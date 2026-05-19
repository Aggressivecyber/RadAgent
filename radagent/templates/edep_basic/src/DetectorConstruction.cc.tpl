#include "DetectorConstruction.hh"

#include "G4Box.hh"
#include "G4LogicalVolume.hh"
#include "G4NistManager.hh"
#include "G4PVPlacement.hh"
#include "G4SystemOfUnits.hh"

namespace B1
{

G4VPhysicalVolume* DetectorConstruction::Construct()
{
  G4NistManager* nist = G4NistManager::Instance();
  G4bool checkOverlaps = true;

  // Target parameters
  G4Material* target_mat = nist->FindOrBuildMaterial("$TARGET_MATERIAL");
  G4double target_halfThickness = 0.5 * $TARGET_THICKNESS * $TARGET_THICKNESS_UNIT;
  G4double target_halfXY = 0.5 * $TARGET_SIZE_XY * $TARGET_SIZE_XY_UNIT;

  // Envelope: slightly larger than target
  G4double env_halfXY = target_halfXY * 1.5;
  G4double env_halfZ = target_halfThickness * 3.0;
  G4Material* env_mat = nist->FindOrBuildMaterial("G4_AIR");

  // World
  G4double world_halfXY = env_halfXY * 1.2;
  G4double world_halfZ = env_halfZ * 1.2;
  G4Material* world_mat = nist->FindOrBuildMaterial("G4_AIR");

  auto solidWorld = new G4Box("World", world_halfXY, world_halfXY, world_halfZ);
  auto logicWorld = new G4LogicalVolume(solidWorld, world_mat, "World");
  auto physWorld = new G4PVPlacement(nullptr, G4ThreeVector(), logicWorld, "World",
                                      nullptr, false, 0, checkOverlaps);

  // Envelope
  auto solidEnv = new G4Box("Envelope", env_halfXY, env_halfXY, env_halfZ);
  auto logicEnv = new G4LogicalVolume(solidEnv, env_mat, "Envelope");
  new G4PVPlacement(nullptr, G4ThreeVector(), logicEnv, "Envelope",
                    logicWorld, false, 0, checkOverlaps);

  // Target slab (centered at origin)
  auto solidTarget = new G4Box("Target", target_halfXY, target_halfXY, target_halfThickness);
  auto logicTarget = new G4LogicalVolume(solidTarget, target_mat, "Target");
  new G4PVPlacement(nullptr, G4ThreeVector(), logicTarget, "Target",
                    logicEnv, false, 0, checkOverlaps);

  fScoringVolume = logicTarget;

  G4cout << "Target: " << target_mat->GetName() << G4endl;
  G4cout << "  Thickness = " << $TARGET_THICKNESS << " $TARGET_THICKNESS_UNIT_STR" << G4endl;
  G4cout << "  Size XY = " << $TARGET_SIZE_XY << " $TARGET_SIZE_XY_UNIT_STR" << G4endl;

  return physWorld;
}

}  // namespace B1
