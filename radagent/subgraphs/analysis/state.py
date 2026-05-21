"""分析子图 State 定义"""

from typing_extensions import TypedDict

from radagent.schemas import (
    AnomalyCheck,
    BuildResult,
    SimulationPlan,
    SimulationResult,
)


class AnalysisState(TypedDict):
    """分析子图独立 state"""
    sim_plan: SimulationPlan
    build: BuildResult
    results: list[SimulationResult]
    anomaly: list[AnomalyCheck]
    figure_paths: dict
    analysis_data: dict
    parse_error: str
