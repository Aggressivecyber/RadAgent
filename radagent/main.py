"""RadG4-Agent CLI 入口"""

import json
import sys

from langgraph.types import Command

from radagent.graph import build_graph
from radagent.log import init_session_log, log_info, get_session_dir
from radagent.memory import MemoryStore
from radagent.config import MEMORY_DB, DEFAULT_USER
from radagent.schemas import BuildResult, ControlState

_IS_PIPE = not sys.stdin.isatty()


def _read_user_input() -> str:
    """读取用户输入（支持多行）"""
    if _IS_PIPE:
        return sys.stdin.read().strip()

    print("  （多行输入，以空行结束）")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "" and lines:
            break
        if line.strip():
            lines.append(line.strip())

    return "\n".join(lines)


def _select_user(memory: MemoryStore):
    """交互式用户选择/创建"""
    from radagent.memory.models import User
    # 列出已有用户
    users = memory.list_users()
    if users:
        print("\n已有用户:")
        for i, u in enumerate(users, 1):
            proj_count = len(memory.list_projects(u.id))
            print(f"  {i}. {u.display_name}  ({proj_count} 个项目)")
        print(f"  {len(users) + 1}. 新建用户")
        print()
        choice = input("选择用户 (编号或名称): ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(users):
                return users[idx]
        # 按名称查找
        for u in users:
            if u.id == choice or u.display_name == choice:
                return u
        # 非空输入 → 新建
        if choice:
            return memory.get_or_create_user(choice, choice)
        # 空输入 → 默认用户
        return memory.get_or_create_user(DEFAULT_USER)

    # 无已有用户
    name = input("\n请输入用户名 (回车使用 default): ").strip()
    if not name:
        name = DEFAULT_USER
    return memory.get_or_create_user(name, name)


def main():
    print("=" * 60)
    print("  RadG4-Agent — 航天辐照仿真智能体")
    print("  输入自然语言，自动完成 Geant4 仿真与报告生成")
    print("=" * 60)

    session_dir = init_session_log()
    memory = MemoryStore(MEMORY_DB)

    # pipe 模式跳过用户选择
    if _IS_PIPE:
        user = memory.get_or_create_user(DEFAULT_USER)
    else:
        user = _select_user(memory)

    graph = build_graph()

    # ── 项目选择 ──────────────────────────────────────────────
    projects = memory.list_projects(user.id)
    project = None
    branch = None
    sim = None
    initial_state = None

    if projects and not _IS_PIPE:
        print(f"\n欢迎, {user.display_name}! 近期项目:")
        for i, p in enumerate(projects[:10], 1):
            print(f"  {i}. [{p.status}] {p.title}  ({p.created_at[:10]})")
        print(f"\n输入编号继续, 或输入新需求开始新项目")

    user_input_raw = _read_user_input()
    if not user_input_raw:
        print("再见！")
        memory.close()
        return

    # 判断是选择已有项目还是新需求
    if projects and not _IS_PIPE and user_input_raw.isdigit():
        idx = int(user_input_raw) - 1
        if 0 <= idx < len(projects):
            project = projects[idx]
            branch = memory.get_main_branch(project.id)
            sim = memory.get_latest_simulation(branch.id)
            # 恢复已有项目：让用户输入修改指令
            print(f"\n项目: {project.title}")
            branches = memory.list_branches(project.id)
            for b in branches:
                latest = memory.get_latest_simulation(b.id)
                status = latest.status if latest else "none"
                print(f"  分支 [{b.label}] → {status}")

            print("\n输入修改指令创建新分支, 或输入新需求")
            mod_input = _read_user_input()
            if not mod_input:
                print("再见！")
                memory.close()
                return

            # 创建新分支
            parent_sim_id = sim.id if sim else ""
            branch = memory.create_branch(
                project_id=project.id,
                label=mod_input[:40],
                parent_branch_id=branch.id,
                parent_sim_id=parent_sim_id,
            )
            user_input = mod_input
            initial_state = None
        else:
            print("无效编号")
            memory.close()
            return
    else:
        user_input = user_input_raw

    # ── 创建项目/仿真记录 ────────────────────────────────────
    log_info("main", f"用户输入: {user_input}")

    if project is None:
        project = memory.create_project(user.id, user_input)
        branch = memory.get_main_branch(project.id)

    sim = memory.create_simulation(branch.id, str(session_dir))

    if initial_state is None:
        initial_state = {
            "messages": [],
            "user_input": user_input,
            "sim_plan": None,
            "build": BuildResult(),
            "results": [],
            "anomaly": [],
            "figure_paths": {},
            "analysis_data": {},
            "report": "",
            "control": ControlState(),
            "parse_error": "",
            "gate_feedback": "",
            "gate_feedback_source": "",
            "simulation_id": sim.id,
        }
    else:
        initial_state["user_input"] = user_input
        initial_state["simulation_id"] = sim.id

    config = {"configurable": {"thread_id": f"radagent-{project.id}-{branch.id}"}}

    print(f"\n--- 开始处理 (日志: {session_dir}, 项目: {project.title}) ---\n")

    # ── 执行管线 ──────────────────────────────────────────────
    _run_stream(graph, initial_state, config)

    # 处理 interrupt
    state_snapshot = graph.get_state(config)
    while state_snapshot.next:
        if not _handle_interrupt(graph, config, state_snapshot, memory, sim.id):
            break
        state_snapshot = graph.get_state(config)

    # ── 更新仿真记录 ──────────────────────────────────────────
    final = graph.get_state(config)
    final_results = final.values.get("results", [])
    final_report = final.values.get("report", "")
    final_plan = final.values.get("sim_plan")

    memory.update_simulation(
        sim.id,
        sim_plan=json.dumps(_to_json_safe(final_plan), ensure_ascii=False) if final_plan else "",
        results=json.dumps([_to_json_safe(r) for r in final_results], ensure_ascii=False) if final_results else "",
        report=final_report,
        status="completed",
        finished_at=MemoryStore._now(),
    )
    memory.update_project_status(project.id, "completed")

    memory.close()
    print("\n完成！")


def _run_stream(graph, initial_state, config):
    """流式执行主图，实时打印节点进展"""
    try:
        for event in graph.stream(initial_state, config=config, stream_mode="updates"):
            for node_name, output in event.items():
                _print_node_update(node_name, output)
    except Exception as e:
        log_info("main", f"流执行错误: {e}")
        print(f"\n错误: {e}")


def _print_node_update(node_name: str, output: dict):
    """根据节点类型打印进展信息"""
    if node_name == "research":
        plan = output.get("sim_plan")
        if plan:
            geo = plan.geometry
            print(f"  [调研完成] 结构: {geo.name}, {len(geo.layers)} 层")
            for s in plan.scenarios:
                print(f"    场景: {s.name} ({s.source.particle} {s.source.energy_MeV} MeV, {s.num_events} events)")
        err = output.get("parse_error")
        if err:
            print(f"  [调研错误] {err[:200]}")

    elif node_name == "parameterize":
        build = output.get("build")
        if build and build.source_dir:
            print(f"  [模板渲染] {build.source_dir}")

    elif node_name == "build_and_run":
        build = output.get("build")
        results = output.get("results", [])
        if build:
            if build.compile_ok:
                print(f"  [编译] 成功")
            if build.run_ok and results:
                for r in results:
                    print(f"  [场景] {r.scenario_name}: "
                          f"剂量={r.total_dose_Gy:.4e} Gy, "
                          f"峰值层={r.peak_layer or 'N/A'}")
            err = build.compile_error
            if err:
                print(f"  [编译失败] {err[:200]}")

    elif node_name == "sim_gate":
        err = output.get("parse_error", "")
        if err:
            print(f"  [门禁 ✗] 仿真结果不达标")
            print(f"    {err[:300]}")
        else:
            print(f"  [门禁 ✓] 仿真结果通过")

    elif node_name == "analyze":
        fig_paths = output.get("figure_paths", {})
        anomaly = output.get("anomaly", [])
        if fig_paths:
            print(f"  [可视化] 生成 {len(fig_paths)} 张图:")
            for key, path in fig_paths.items():
                print(f"    {key}: {path}")
        for a in anomaly:
            if a.status != "normal":
                print(f"  [异常] {a.status}: {a.details}")

    elif node_name == "report_gate":
        err = output.get("parse_error", "")
        if err:
            print(f"  [门禁 ✗] 报告质量不达标")
            print(f"    {err[:300]}")
        else:
            print(f"  [门禁 ✓] 报告质量通过")

    elif node_name == "generate_report":
        report = output.get("report", "")
        print(f"\n  [报告] 已生成 ({len(report)} 字)")

    elif node_name == "human_review":
        pass

    elif node_name == "revise":
        print(f"  [修订] 分析中...")


def _handle_interrupt(graph, config, snapshot, memory, sim_id) -> bool:
    """处理 interrupt，返回 True 表示继续"""
    if not snapshot.tasks:
        return False

    for task in snapshot.tasks:
        if not hasattr(task, "interrupts") or not task.interrupts:
            continue

        info = task.interrupts[0].value

        if info.get("type") == "plan_confirmation":
            print("\n" + "=" * 50)
            print("仿真计划确认")
            print("=" * 50)
            message = info.get("message", "")
            if isinstance(message, str):
                print(message[:1500])
            else:
                print(str(message)[:1500])

            if _IS_PIPE:
                print("\n[pipe 模式] 自动确认")
                decision = "yes"
            else:
                decision = input("\n输入 'yes' 确认，或输入修改意见: ").strip()

            if decision.lower() == "yes" or not decision:
                resume_value = {"action": "confirm"}
            else:
                resume_value = {"action": "modify", "feedback": decision}

        elif info.get("type") == "gate_warning":
            gate_name = info.get("gate_name", "unknown")
            print(f"\n{'=' * 50}")
            print(f"门禁警告 [{gate_name}]")
            print("=" * 50)
            message = info.get("message", "")
            print(message[:2000])

            if _IS_PIPE:
                print("\n[pipe 模式] 自动继续")
                decision = "continue"
            else:
                decision = input("\n输入 'continue' 继续，或输入修改意见回退: ").strip().lower()

            if decision == "continue" or decision == "yes" or not decision:
                resume_value = {"action": "continue"}
            else:
                resume_value = {"action": "modify", "feedback": decision}

        else:
            print("\n" + "=" * 50)
            print("报告审核")
            print("=" * 50)
            preview = info.get("report_preview", "")
            print(f"\n{preview}...\n")

            if _IS_PIPE:
                print("[pipe 模式] 自动批准")
                decision = "yes"
            else:
                decision = input("输入 'yes' 批准，或输入反馈意见: ").strip()

            if decision.lower() == "yes" or not decision:
                resume_value = {"approved": True, "feedback": ""}
            else:
                resume_value = {"approved": False, "feedback": decision}

        log_info("main", f"用户决定: {decision}")

        # 记录用户决策到 L2
        try:
            memory.append_attempt(
                simulation_id=sim_id,
                node="interrupt",
                user_action=str(resume_value.get("action", resume_value.get("approved", ""))),
                user_feedback=resume_value.get("feedback", ""),
            )
        except Exception as e:
            log_info("main", f"记忆写入失败: {e}")

        try:
            graph.invoke(Command(resume=resume_value), config=config)
        except Exception as e:
            log_info("main", f"恢复执行错误: {e}")
            print(f"错误: {e}")
            return False

        return True

    return False


def _to_json_safe(obj):
    """递归转换为 JSON 安全类型"""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(i) for i in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_json_safe(getattr(obj, k)) for k in obj.__dataclass_fields__}
    return str(obj)


if __name__ == "__main__":
    main()
