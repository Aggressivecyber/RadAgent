"""RadG4-Agent CLI 入口"""

from langgraph.types import Command

from radagent.graph import build_graph
from radagent.log import init_session_log, log_info, get_session_dir
from radagent.schemas import BuildResult, ControlState, SimulationResult


def main():
    print("=" * 60)
    print("RadG4-Agent — 辐照仿真智能体")
    print("输入自然语言描述，自动完成 Geant4 仿真和报告生成")
    print("=" * 60)

    # 初始化日志
    session_dir = init_session_log()

    graph = build_graph()
    config = {"configurable": {"thread_id": "radagent-v1"}}

    user_input = input("\n请描述辐照仿真需求:\n> ").strip()
    if not user_input:
        print("再见！")
        return

    log_info("main", f"用户输入: {user_input}")

    # 初始状态
    initial_state = {
        "messages": [],
        "user_input": user_input,
        "sim_params": None,
        "build": BuildResult(),
        "result": SimulationResult(),
        "anomaly": [],
        "report": "",
        "control": ControlState(),
        "parse_error": "",
    }

    print(f"\n--- 开始处理 (日志: {session_dir}) ---")

    # 第一次运行 — 会在 human_review 的 interrupt 处暂停
    try:
        for event in graph.stream(initial_state, config=config, stream_mode="updates"):
            for node_name, node_output in event.items():
                if node_name == "parse_intent":
                    params = node_output.get("sim_params")
                    if params:
                        print(f"\n参数提取完成:")
                        print(f"   粒子: {params.particle.particle} {params.particle.energy_MeV} MeV")
                        print(f"   材料: {params.material.name} ({params.material.geant4_name})")
                        print(f"   厚度: {params.material.thickness_um} um")
                elif node_name == "parameterize":
                    print(f"  -> 模板渲染完成")
                elif node_name == "build_and_run":
                    build = node_output.get("build")
                    if build:
                        status = "成功" if build.run_ok else "失败"
                        print(f"  -> 仿真执行: {status}")
                elif node_name == "analyze":
                    result = node_output.get("result")
                    if result and result.num_events > 0:
                        print(f"  -> 结果: 剂量={result.total_dose_Gy:.4e}")
                elif node_name == "generate_report":
                    report = node_output.get("report", "")
                    print(f"\n报告已生成 ({len(report)} 字)")
    except Exception as e:
        log_info("main", f"流执行错误: {e}")
        print(f"\n错误: {e}")
        return

    # 处理 interrupt — 等待用户审核
    state_snapshot = graph.get_state(config)
    while state_snapshot.next:
        print("\n" + "=" * 40)
        print("报告审核")

        if state_snapshot.tasks:
            for task in state_snapshot.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    info = task.interrupts[0].value
                    preview = info.get("report_preview", "")
                    print(f"\n报告预览:\n{preview}...\n")

        decision = input("输入 'yes' 批准，或输入反馈意见要求重新分析: ").strip().lower()

        if decision == "yes":
            resume_value = {"approved": True, "feedback": ""}
        else:
            resume_value = {"approved": False, "feedback": decision or "请重新分析"}

        log_info("main", f"用户审核决定: {decision}")

        try:
            graph.invoke(Command(resume=resume_value), config=config)
        except Exception as e:
            log_info("main", f"恢复执行错误: {e}")
            print(f"错误: {e}")
            break

        state_snapshot = graph.get_state(config)

    print("\n完成！")


if __name__ == "__main__":
    main()
