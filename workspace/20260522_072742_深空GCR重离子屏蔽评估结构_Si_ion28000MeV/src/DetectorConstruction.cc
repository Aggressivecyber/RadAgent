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

  G4double halfXY = 0.5 * 20.0 * cm;

  // 计算总厚度
  G4double totalThickness = 0.0;
  G4double thickness_0 = 3.0 * mm;
  G4double thickness_1 = 20.0 * mm;
  G4double thickness_2 = 5.0 * mm;
  G4double thickness_3 = 100.0 * mm;
  totalThickness = 128.0 * mm;

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
    auto solid = new G4Box("铝合金舱体外壳", halfXY, halfXY, 0.5 * thickness_0);
    auto logic = new G4LogicalVolume(solid, nist->FindOrBuildMaterial("G4_Al"), "铝合金舱体外壳");
    zOffset -= 0.5 * thickness_0;
    new G4PVPlacement(nullptr, G4ThreeVector(0, 0, zOffset), logic, "铝合金舱体外壳",
                      logicWorld, false, 0, checkOverlaps);
    zOffset -= 0.5 * thickness_0;
    fLayerVolumes.push_back(logic);
  }

  {
    auto solid = new G4Box("聚乙烯辐射防护层", halfXY, halfXY, 0.5 * thickness_1);
    auto logic = new G4LogicalVolume(solid, nist->FindOrBuildMaterial("G4_POLYETHYLENE"), "聚乙烯辐射防护层");
    zOffset -= 0.5 * thickness_1;
    new G4PVPlacement(nullptr, G4ThreeVector(0, 0, zOffset), logic, "聚乙烯辐射防护层",
                      logicWorld, false, 0, checkOverlaps);
    zOffset -= 0.5 * thickness_1;
    fLayerVolumes.push_back(logic);
  }

  {
    auto solid = new G4Box("凯夫拉结构层", halfXY, halfXY, 0.5 * thickness_2);
    auto logic = new G4LogicalVolume(solid, nist->FindOrBuildMaterial("G4_KEVLAR"), "凯夫拉结构层");
    zOffset -= 0.5 * thickness_2;
    new G4PVPlacement(nullptr, G4ThreeVector(0, 0, zOffset), logic, "凯夫拉结构层",
                      logicWorld, false, 0, checkOverlaps);
    zOffset -= 0.5 * thickness_2;
    fLayerVolumes.push_back(logic);
  }

  {
    auto solid = new G4Box("水模体", halfXY, halfXY, 0.5 * thickness_3);
    auto logic = new G4LogicalVolume(solid, nist->FindOrBuildMaterial("G4_WATER"), "水模体");
    zOffset -= 0.5 * thickness_3;
    new G4PVPlacement(nullptr, G4ThreeVector(0, 0, zOffset), logic, "水模体",
                      logicWorld, false, 0, checkOverlaps);
    zOffset -= 0.5 * thickness_3;
    fScoringVolume = logic;
    fLayerVolumes.push_back(logic);
  }


  // 逐层设置截断距离: cut = thickness / 4
  {
    auto region_0 = new G4Region("铝合金舱体外壳_region");
    auto cuts_0 = new G4ProductionCuts();
    cuts_0->SetProductionCut(0.75 * mm);
    region_0->SetProductionCuts(cuts_0);
    fLayerVolumes[0]->SetRegion(region_0);
    region_0->AddRootLogicalVolume(fLayerVolumes[0]);
  }
  {
    auto region_1 = new G4Region("聚乙烯辐射防护层_region");
    auto cuts_1 = new G4ProductionCuts();
    cuts_1->SetProductionCut(5.0 * mm);
    region_1->SetProductionCuts(cuts_1);
    fLayerVolumes[1]->SetRegion(region_1);
    region_1->AddRootLogicalVolume(fLayerVolumes[1]);
  }
  {
    auto region_2 = new G4Region("凯夫拉结构层_region");
    auto cuts_2 = new G4ProductionCuts();
    cuts_2->SetProductionCut(1.25 * mm);
    region_2->SetProductionCuts(cuts_2);
    fLayerVolumes[2]->SetRegion(region_2);
    region_2->AddRootLogicalVolume(fLayerVolumes[2]);
  }
  {
    auto region_3 = new G4Region("水模体_region");
    auto cuts_3 = new G4ProductionCuts();
    cuts_3->SetProductionCut(25.0 * mm);
    region_3->SetProductionCuts(cuts_3);
    fLayerVolumes[3]->SetRegion(region_3);
    region_3->AddRootLogicalVolume(fLayerVolumes[3]);
  }

  return physWorld;
}

}  // namespace B1
