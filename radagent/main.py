"""RadG4-Agent CLI 入口"""

from langgraph.types import Command

from radagent.graph import build_graph
from radagent.log import init_session_log, log_info, get_session_dir
from radagent.schemas import BuildResult, ControlState


def main():
    print("=" * 60)
    print("  RadG4-Agent — 航天辐照仿真智能体")
    print("  输入自然语言，自动完成 Geant4 仿真与报告生成")
    print("=" * 60)

    session_dir = init_session_log()
    graph = build_graph()
    config = {"configurable": {"thread_id": "radagent-v1"}}

    user_input = input("\n请描述辐照仿真需求:\n> ").strip()
    if not user_input:
        print("再见！")
        return

    log_info("main", f"用户输入: {user_input}")

    initial_state = {
        "messages": [],
        "user_input": user_input,
        "sim_plan": None,
        "build": BuildResult(),
        "results": [],
        "anomaly": [],
        "figure_paths": {},
        "report": "",
        "control": ControlState(),
        "parse_error": "",
    }

    print(f"\n--- 开始处理 (日志: {session_dir}) ---\n")

    # 阶段 1: 流式执行，处理子图中的 interrupt（confirm_params）
    _run_stream(graph, initial_state, config)

    # 阶段 2: 处理剩余 interrupt（human_review）
    state_snapshot = graph.get_state(config)
    while state_snapshot.next:
        if not _handle_interrupt(graph, config, state_snapshot):
            break
        state_snapshot = graph.get_state(config)

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

    elif node_name == "generate_report":
        report = output.get("report", "")
        print(f"\n  [报告] 已生成 ({len(report)} 字)")

    elif node_name == "human_review":
        pass  # 在 _handle_interrupt 中处理


def _handle_interrupt(graph, config, snapshot) -> bool:
    """处理 interrupt（confirm_params 或 human_review），返回 True 表示继续"""
    if not snapshot.tasks:
        return False

    for task in snapshot.tasks:
        if not hasattr(task, "interrupts") or not task.interrupts:
            continue

        info = task.interrupts[0].value

        # 区分确认类型
        if info.get("type") == "plan_confirmation":
            # confirm_params: 显示仿真计划
            print("\n" + "=" * 50)
            print("仿真计划确认")
            print("=" * 50)
            message = info.get("message", "")
            if isinstance(message, str):
                print(message[:1500])
            else:
                print(str(message)[:1500])

            decision = input("\n输入 'yes' 确认，或输入修改意见: ").strip()
            if decision.lower() == "yes":
                resume_value = {"action": "confirm"}
            else:
                resume_value = {"action": "modify", "feedback": decision or "请重新设计"}

        else:
            # human_review: 报告审核
            print("\n" + "=" * 50)
            print("报告审核")
            print("=" * 50)
            preview = info.get("report_preview", "")
            print(f"\n{preview}...\n")

            decision = input("输入 'yes' 批准，或输入反馈意见: ").strip()
            if decision.lower() == "yes":
                resume_value = {"approved": True, "feedback": ""}
            else:
                resume_value = {"approved": False, "feedback": decision or "请重新分析"}

        log_info("main", f"用户决定: {decision}")

        try:
            graph.invoke(Command(resume=resume_value), config=config)
        except Exception as e:
            log_info("main", f"恢复执行错误: {e}")
            print(f"错误: {e}")
            return False

        return True

    return False


if __name__ == "__main__":
    main()
