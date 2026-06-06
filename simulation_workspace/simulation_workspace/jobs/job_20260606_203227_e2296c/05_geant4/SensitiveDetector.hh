#ifndef SensitiveDetector_h
#define SensitiveDetector_h 1

#include "G4VSensitiveDetector.hh"
#include "globals.hh"

class G4Step;
class G4HCofThisEvent;

class SensitiveDetector : public G4VSensitiveDetector {
public:
  SensitiveDetector(const G4String& name);
  virtual ~SensitiveDetector();

  void SetVoxelParams(G4double voxelSize, G4double sizeX, G4double sizeY, G4double sizeZ);

  virtual void Initialize(G4HCofThisEvent* hce) override;
  virtual G4bool ProcessHits(G4Step* step, G4TouchableHistory* history) override;

private:
  G4double fVoxelSize;
  G4double fTargetSizeX, fTargetSizeY, fTargetSizeZ;
};

#endif
