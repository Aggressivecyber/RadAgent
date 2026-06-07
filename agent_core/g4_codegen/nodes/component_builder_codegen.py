"""Component Builder Codegen — generates C++ for individual detector components.

Each non-world component gets its own geometry construction code.
"""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.schemas import G4CodegenSubgraphState


async def component_builder_codegen(state: G4CodegenSubgraphState) -> dict[str, Any]:
    """Generate C++ for individual detector components."""
    model_ir = state.get("g4_model_ir", {})
    components = model_ir.get("components", [])
    errors = list(state.get("errors", []))

    code_blocks: list[str] = []

    for comp in components:
        if comp.get("component_type") == "world":
            continue

        cid = comp.get("component_id", "unknown")
        display = comp.get("display_name", cid)
        geo_type = comp.get("geometry_type", "box")
        dims = comp.get("dimensions", {})
        material = comp.get("material_id", "G4_AIR")

        safe_name = cid.replace("-", "_").replace(" ", "_")

        if geo_type == "box":
            dx = dims.get("dx", 10)
            dy = dims.get("dy", 10)
            dz = dims.get("dz", 10)
            code_blocks.append(_box_component(safe_name, display, dx, dy, dz, material))
        elif geo_type == "cylinder" or geo_type == "tubs":
            rmin = dims.get("rmin", 0)
            rmax = dims.get("rmax", 10)
            dz = dims.get("dz", 10)
            code_blocks.append(_cylinder_component(safe_name, display, rmin, rmax, dz, material))
        else:
            code_blocks.append(f"// TODO: {safe_name} — unsupported geometry type: {geo_type}")

    code = "\n\n".join(code_blocks) if code_blocks else "// No non-world components"

    return {
        "component_builder_code": code,
        "errors": errors,
        "current_node": "component_builder_codegen",
    }


def _box_component(
    name: str, display: str, dx: float, dy: float, dz: float, material: str
) -> str:
    return f"""// Component: {display} (box)
auto {name}_solid = new G4Box("{name}", {dx}, {dy}, {dz});
auto {name}_logic = new G4LogicalVolume(
    {name}_solid,
    G4NistManager::Instance()->FindOrBuildMaterial("{material}"),
    "{name}_logic");
"""


def _cylinder_component(
    name: str, display: str, rmin: float, rmax: float, dz: float, material: str
) -> str:
    return f"""// Component: {display} (cylinder)
auto {name}_solid = new G4Tubs("{name}", {rmin}, {rmax}, {dz}, 0, CLHEP::twopi);
auto {name}_logic = new G4LogicalVolume(
    {name}_solid,
    G4NistManager::Instance()->FindOrBuildMaterial("{material}"),
    "{name}_logic");
"""
