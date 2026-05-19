"""节点: 解析仿真结果 + NPU 异常检测 stub"""

from radagent.state import RadAgentState
from radagent.schemas import AnomalyCheck, SimulationResult
from radagent.tools.geant4_tools import parse_geant4_output


def analyze(state: RadAgentState) -> dict:
    """解析 Geant4 输出，运行异常检测"""
    build = state.get("build")

    # 解析结果
    result = parse_geant4_output(build.run_stdout if build else "")

    if result.num_events > 0:
        print(f"  📊 结果: 总剂量={result.total_dose_Gy:.4e}, "
              f"每事件={result.dose_per_event_Gy:.4e}, "
              f"穿透={result.penetrated}")
    else:
        print(f"  ⚠️ 无法解析仿真输出")

    # NPU 异常检测 stub
    anomaly = _npu_anomaly_check(result)

    return {"result": result, "anomaly": [anomaly]}


def _npu_anomaly_check(result: SimulationResult) -> AnomalyCheck:
    """NPU 异常检测 stub — 后续替换为 ONNX 模型"""
    if result.num_events == 0:
        return AnomalyCheck(status="high_risk", details="仿真无有效输出")

    if result.total_dose_Gy <= 0:
        return AnomalyCheck(status="suspicious", details="总能量沉积为0，可能配置有误")

    if result.dose_per_event_Gy > 1e6:
        return AnomalyCheck(status="suspicious", details="单事件剂量异常高，请检查能量设置")

    return AnomalyCheck(status="normal", details="")
