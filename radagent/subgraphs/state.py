"""调研子图 State 定义"""

from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from typing_extensions import TypedDict

from radagent.schemas import (
    OrbitEnvironment,
    ShieldGeometry,
    SimulationPlan,
    SimulationScenario,
)


class ResearchState(TypedDict):
    """调研子图独立 state"""
    messages: Annotated[list[AnyMessage], add_messages]
    user_input: str
    intent_data: dict
    geometry: ShieldGeometry
    orbit: OrbitEnvironment
    scenarios: list[SimulationScenario]
    orbit_env_data: dict
    search_results: str
    sim_plan: SimulationPlan | None
    parse_error: str
    unresolved_materials: list[str]
    unresolved_particles: list[str]
