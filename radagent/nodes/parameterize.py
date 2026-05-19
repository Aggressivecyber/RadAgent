"""节点: 渲染 Geant4 模板（确定性，无 LLM）"""

from radagent.state import RadAgentState
from radagent.schemas import BuildResult
from radagent.tools.geant4_tools import render_template


def parameterize(state: RadAgentState) -> dict:
    """将仿真参数渲染到 Geant4 模板"""
    params = state["sim_params"]

    source_dir, files = render_template("edep_basic", params)

    print(f"  📦 模板渲染完成: {source_dir}")
    print(f"     粒子: {params.particle.particle} {params.particle.energy_MeV} MeV")
    print(f"     材料: {params.material.geant4_name} ({params.material.name})")
    print(f"     厚度: {params.material.thickness_um} um")
    print(f"     物理: {params.physics_list}")
    print(f"     事件: {params.num_events}")

    return {
        "build": BuildResult(source_dir=source_dir),
    }
