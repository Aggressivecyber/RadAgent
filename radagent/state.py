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
    parse_error: str
