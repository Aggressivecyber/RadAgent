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

  G4double halfXY = 0.5 * 10.0 * cm;

  // 计算总厚度
  G4double totalThickness = 0.0;
  G4double thickness_0 = 10.0 * mm;
  G4double thickness_1 = 0.04 * mm;
  G4double thickness_2 = 0.02 * mm;
  totalThickness = 10.06 * mm;

  // World
  G4double world_halfXY = halfXY * 1.5;
  G4double world_halfZ = totalThickness * 0.75;
  auto solidWorld = new G4Box("World", world_halfXY, world_halfXY, world_halfZ);
  auto logicWorld = new G4LogicalVolume(solidWorld, nist->FindOrBuildMaterial("G4_AIR"), "World");
  auto physWorld = new G4PVPlacement(nullptr, G4ThreeVector(), logicWorld, "World",
                                      nullptr, false, 0, checkOverlaps);

  // 自定义材料定义


  // 逐层构建（从外到内，沿 -Z 方向堆叠）
  G4double zOffset = totalThickness / 2.0;
  {
    auto solid = new G4Box("铝板", halfXY, halfXY, 0.5 * thickness_0);
    auto logic = new G4LogicalVolume(solid, nist->FindOrBuildMaterial("G4_Al"), "铝板");
    zOffset -= 0.5 * thickness_0;
    new G4PVPlacement(nullptr, G4ThreeVector(0, 0, zOffset), logic, "铝板",
                      logicWorld, false, 0, checkOverlaps);
    zOffset -= 0.5 * thickness_0;
    fLayerVolumes.push_back(logic);
  }

  {
    auto solid = new G4Box("石墨", halfXY, halfXY, 0.5 * thickness_1);
    auto logic = new G4LogicalVolume(solid, nist->FindOrBuildMaterial("G4_C"), "石墨");
    zOffset -= 0.5 * thickness_1;
    new G4PVPlacement(nullptr, G4ThreeVector(0, 0, zOffset), logic, "石墨",
                      logicWorld, false, 0, checkOverlaps);
    zOffset -= 0.5 * thickness_1;
    fLayerVolumes.push_back(logic);
  }

  {
    auto solid = new G4Box("硅基器件", halfXY, halfXY, 0.5 * thickness_2);
    auto logic = new G4LogicalVolume(solid, nist->FindOrBuildMaterial("G4_Si"), "硅基器件");
    zOffset -= 0.5 * thickness_2;
    new G4PVPlacement(nullptr, G4ThreeVector(0, 0, zOffset), logic, "硅基器件",
                      logicWorld, false, 0, checkOverlaps);
    zOffset -= 0.5 * thickness_2;
    fScoringVolume = logic;
    fLayerVolumes.push_back(logic);
  }


  // 逐层设置截断距离: cut = thickness / 4
  {
    auto region_0 = new G4Region("铝板_region");
    auto cuts_0 = new G4ProductionCuts();
    cuts_0->SetProductionCut(2.5 * mm);
    region_0->SetProductionCuts(cuts_0);
    fLayerVolumes[0]->SetRegion(region_0);
    region_0->AddRootLogicalVolume(fLayerVolumes[0]);
  }
  {
    auto region_1 = new G4Region("石墨_region");
    auto cuts_1 = new G4ProductionCuts();
    cuts_1->SetProductionCut(0.01 * mm);
    region_1->SetProductionCuts(cuts_1);
    fLayerVolumes[1]->SetRegion(region_1);
    region_1->AddRootLogicalVolume(fLayerVolumes[1]);
  }
  {
    auto region_2 = new G4Region("硅基器件_region");
    auto cuts_2 = new G4ProductionCuts();
    cuts_2->SetProductionCut(0.005 * mm);
    region_2->SetProductionCuts(cuts_2);
    fLayerVolumes[2]->SetRegion(region_2);
    region_2->AddRootLogicalVolume(fLayerVolumes[2]);
  }

  return physWorld;
}

}  // namespace B1
