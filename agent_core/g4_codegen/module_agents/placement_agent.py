"""Placement module agent — generates PlacementManager.hh/cc."""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import ModuleAgentResult

PLACEMENT_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 放置模块编码 Agent。

你只负责 PlacementManager.hh 和 PlacementManager.cc。

职责：
1. 管理 G4PVPlacement 实例
2. 处理 mother-child 关系
3. 应用平移和旋转
4. checkOverlaps 配置

严格要求：
1. 只生成 PlacementManager 相关文件
2. 不得生成 source、physics 等
3. 只输出 include/PlacementManager.hh 和 src/PlacementManager.cc
4. 不得生成 main.cc、DetectorConstruction、CMakeLists.txt 或宏文件
5. 不得直接创建材料或调用 G4NistManager；材料由 geometry/material 模块提供
6. 调用 G4PVPlacement(rotation, position, logical, name, mother, ...) 时，
   rotation 参数必须是 G4RotationMatrix*，不要使用 const G4RotationMatrix*
   推荐公开接口：
   PlaceVolume(G4RotationMatrix* rotation, const G4ThreeVector& position,
               G4LogicalVolume* logical, const G4String& name,
               G4LogicalVolume* mother, G4bool many, G4int copyNo,
               G4bool checkOverlaps)
   返回类型建议使用 G4VPhysicalVolume*。如果提供 static Place(...) 兼容接口，
   也应返回 G4VPhysicalVolume*，并直接返回 PlaceVolume(...) 的结果。
   如果 PlacementManager.hh 的公开声明返回或引用 G4PVPlacement*，头文件必须
   include G4PVPlacement.hh 或声明 class G4PVPlacement;，不能只在 .cc 中 include。
7. 如果提供 G4Transform3D overload，传给 G4PVPlacement 前必须使用非 const 局部副本，
   例如 G4Transform3D placementTransform = transform;
   new G4PVPlacement(placementTransform, logical, name, mother, ...)
8. 不要把 const G4Transform3D& 直接传给 G4PVPlacement 构造函数
9. 输出 JSON 格式
"""


async def run_placement_agent(
    module_context: dict[str, Any],
) -> ModuleAgentResult:
    """Run placement module agent."""
    return await run_module_agent(
        module_name="placement",
        module_context=module_context,
        system_prompt=PLACEMENT_SYSTEM_PROMPT,
    )
