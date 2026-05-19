import operator
from typing import Annotated, Any

from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages

from radagent.schemas import (
    AnomalyCheck,
    BuildResult,
    ControlState,
    SimulationParams,
    SimulationResult,
)


class RadAgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    user_input: str
    sim_params: SimulationParams
    build: BuildResult
    result: SimulationResult
    anomaly: Annotated[list[AnomalyCheck], operator.add]
    report: str
    control: ControlState
    parse_error: str
