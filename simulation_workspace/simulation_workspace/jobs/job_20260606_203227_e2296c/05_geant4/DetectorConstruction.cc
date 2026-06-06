#include "DetectorConstruction.hh"
#include "G4Box.hh"
#include "G4LogicalVolume.hh"
#include "G4PVPlacement.hh"
#include "G4NistManager.hh"
#include "G4SystemOfUnits.hh"
#include "SensitiveDetector.hh"
#include "G4SDManager.hh"

DetectorConstruction::DetectorConstruction()
  : G4VUserDetectorConstruction(),
    fTargetSizeX(1000.0 * um),
    fTargetSizeY(1000.0 * um),
    fTargetSizeZ(300.0 * um),
    fVoxelSize(50.0 * um),
    fTargetCenter(0., 0., 0.),
    fTargetLogical(nullptr),
    fTargetMaterial(nullptr)
{}

DetectorConstruction::~DetectorConstruction()
{}

G4VPhysicalVolume* DetectorConstruction::Construct() {
  // World
  G4double worldSizeX = 2000.0 * um;
  G4double worldSizeY = 2000.0 * um;
  G4double worldSizeZ = 1000.0 * um;
  G4Box* worldBox = new G4Box("World", worldSizeX/2, worldSizeY/2, worldSizeZ/2);
  G4NistManager* nist = G4NistManager::Instance();
  G4Material* worldMat = nist->FindOrBuildMaterial("G4_AIR");
  G4LogicalVolume* worldLogical = new G4LogicalVolume(worldBox, worldMat, "World");
  G4VPhysicalVolume* worldPhys = new G4PVPlacement(0, G4ThreeVector(), worldLogical, "World", 0, false, 0);

  // Target
  G4Box* targetBox = new G4Box("Target", fTargetSizeX/2, fTargetSizeY/2, fTargetSizeZ/2);
  fTargetMaterial = nist->FindOrBuildMaterial("G4_Si");
  fTargetLogical = new G4LogicalVolume(targetBox, fTargetMaterial, "Target");
  new G4PVPlacement(0, fTargetCenter, fTargetLogical, "Target", worldLogical, false, 0);

  // Sensitive detector
  SensitiveDetector* sensDet = new SensitiveDetector("TargetSD");
  sensDet->SetVoxelParams(fVoxelSize, fTargetSizeX, fTargetSizeY, fTargetSizeZ);
  fTargetLogical->SetSensitiveDetector(sensDet);
  G4SDManager::GetSDMpointer()->AddNewDetector(sensDet);

  return worldPhys;
}
