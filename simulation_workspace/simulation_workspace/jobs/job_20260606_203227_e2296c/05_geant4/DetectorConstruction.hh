#ifndef DetectorConstruction_h
#define DetectorConstruction_h 1

#include "G4VUserDetectorConstruction.hh"
#include "globals.hh"
#include "G4ThreeVector.hh"

class G4LogicalVolume;
class G4VPhysicalVolume;
class G4Material;

class DetectorConstruction : public G4VUserDetectorConstruction {
public:
  DetectorConstruction();
  virtual ~DetectorConstruction();

  virtual G4VPhysicalVolume* Construct();

  // Accessors for target dimensions and voxel size
  G4double GetTargetSizeX() const { return fTargetSizeX; }
  G4double GetTargetSizeY() const { return fTargetSizeY; }
  G4double GetTargetSizeZ() const { return fTargetSizeZ; }
  G4double GetVoxelSize() const { return fVoxelSize; }
  G4ThreeVector GetTargetCenter() const { return fTargetCenter; }

private:
  G4double fTargetSizeX, fTargetSizeY, fTargetSizeZ;
  G4double fVoxelSize;
  G4ThreeVector fTargetCenter;
  G4LogicalVolume* fTargetLogical;
  G4Material* fTargetMaterial;
};

#endif
