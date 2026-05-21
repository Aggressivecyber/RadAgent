"""节点: 分析仿真结果 + 异常检测"""

from radagent.log import log_node_entry, log_node_exit, log_info, log_error
from radagent.state import RadAgentState
from radagent.schemas import AnomalyCheck, SimulationResult

_NODE = "analyze"


def analyze(state: RadAgentState) -> dict:
    """分析多场景仿真结果，运行异常检测"""
    log_node_entry(_NODE, state)

    results = state.get("results", [])
    plan = state.get("sim_plan")

    if not results:
        log_error(_NODE, "无仿真结果可供分析")
        anomaly = AnomalyCheck(status="high_risk", details="无仿真输出")
        update = {"anomaly": [anomaly]}
        log_node_exit(_NODE, "generate_report", update)
        return update

    # 汇总分析
    for result in results:
        if result.num_events > 0:
            log_info(_NODE, f"[{result.scenario_name}] "
                     f"总剂量={result.total_dose_Gy:.4e} Gy, "
                     f"每事件={result.dose_per_event_Gy:.4e} Gy")
            if result.layer_doses:
                for layer, dose in result.layer_doses.items():
                    log_info(_NODE, f"  {layer}: {dose:.4e} J")
        else:
            log_error(_NODE, f"[{result.scenario_name}] 无法解析输出")

    # 异常检测
    anomaly = _check_anomalies(results, plan)
    log_info(_NODE, f"异常检测: status={anomaly.status}, details={anomaly.details or '无异常'}")

    update = {"anomaly": [anomaly]}
    log_node_exit(_NODE, "generate_report", update)
    return update


def _check_anomalies(results: list[SimulationResult], plan) -> AnomalyCheck:
    """多场景异常检测"""
    details = []

    # 检查是否有有效结果
    valid_results = [r for r in results if r.num_events > 0]
    if not valid_results:
        return AnomalyCheck(status="high_risk", details="所有场景均无有效输出")

    # 检查零剂量
    zero_dose = [r.scenario_name for r in valid_results if r.total_dose_Gy <= 0]
    if zero_dose:
        details.append(f"零剂量场景: {', '.join(zero_dose)}")

    # 检查异常高剂量
    for r in valid_results:
        if r.dose_per_event_Gy > 1e6:
            details.append(f"单事件剂量异常高 ({r.scenario_name}: {r.dose_per_event_Gy:.2e} Gy)")

    # 检查敏感体积是否受辐照
    if plan and plan.geometry.sensitive_volume:
        sensitive_hit = False
        for r in valid_results:
            if plan.geometry.sensitive_volume in r.layer_doses:
                if r.layer_doses[plan.geometry.sensitive_volume] > 0:
                    sensitive_hit = True
                    break
        if not sensitive_hit:
            details.append(f"敏感体积 '{plan.geometry.sensitive_volume}' 未被粒子命中")

    if details:
        return AnomalyCheck(status="suspicious", details="; ".join(details))

    return AnomalyCheck(status="normal", details="")
