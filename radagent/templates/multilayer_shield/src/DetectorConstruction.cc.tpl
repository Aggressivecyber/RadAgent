#include "DetectorConstruction.hh"

#include "G4Box.hh"
#include "G4Element.hh"
#include "G4Isotope.hh"
#include "G4LogicalVolume.hh"
#include "G4Material.hh"
#include "G4NistManager.hh"
#include "G4PVPlacement.hh"
#include "G4ProductionCuts.hh"
#include "G4Region.hh"
#include "G4SystemOfUnits.hh"

namespace B1
{

DetectorConstruction::DetectorConstruction()
{}

G4VPhysicalVolume* DetectorConstruction::Construct()
{
  G4NistManager* nist = G4NistManager::Instance();
  G4bool checkOverlaps = true;

  G4double halfXY = 0.5 * $SIZE_XY * cm;

  // 计算总厚度
  G4double totalThickness = 0.0;
$TOTAL_THICKNESS_CALC
  totalThickness = $TOTAL_THICKNESS_SUM;

  // World
  G4double world_halfXY = halfXY * 1.5;
  G4double world_halfZ = totalThickness * 0.75;
  auto solidWorld = new G4Box("World", world_halfXY, world_halfXY, world_halfZ);
  auto logicWorld = new G4LogicalVolume(solidWorld, nist->FindOrBuildMaterial("G4_AIR"), "World");
  auto physWorld = new G4PVPlacement(nullptr, G4ThreeVector(), logicWorld, "World",
                                      nullptr, false, 0, checkOverlaps);

  // 自定义材料定义
$CUSTOM_MATERIAL_DEFS

  // 逐层构建（从外到内，沿 -Z 方向堆叠）
  G4double zOffset = totalThickness / 2.0;
$LAYER_CONSTRUCTION

  // 逐层设置截断距离: cut = thickness / 4
$LAYER_CUTS

  return physWorld;
}

}  // namespace B1
