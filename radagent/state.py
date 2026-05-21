import operator
from typing import Annotated

from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages

from radagent.schemas import (
    AnomalyCheck,
    BuildResult,
    ControlState,
    SimulationPlan,
    SimulationResult,
)


def _last_value(old, new):
    """Reducer: 新值覆盖旧值，无新值时保留旧值"""
    return new if new is not None else old


class RadAgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    user_input: str
    sim_plan: SimulationPlan
    build: BuildResult
    results: Annotated[list[SimulationResult], operator.add]
    anomaly: Annotated[list[AnomalyCheck], operator.add]
    figure_paths: dict
    report: str
    control: ControlState
    parse_error: Annotated[str, _last_value]
    gate_feedback: str
