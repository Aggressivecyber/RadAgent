#ifndef DetectorConstruction_h
#define DetectorConstruction_h 1

#include "G4VUserDetectorConstruction.hh"
#include "globals.hh"
#include <vector>

class G4LogicalVolume;

namespace B1
{

struct LayerInfo {
    G4String name;
    G4String material;
    G4double thickness;
    G4double halfXY;
    G4String role;  // shield, insulation, structure, sensitive
};

class DetectorConstruction : public G4VUserDetectorConstruction
{
  public:
    DetectorConstruction();
    ~DetectorConstruction() override = default;

    G4VPhysicalVolume* Construct() override;
    G4LogicalVolume* GetScoringVolume() const { return fScoringVolume; }
    const std::vector<G4LogicalVolume*>& GetLayerVolumes() const { return fLayerVolumes; }

  private:
    G4LogicalVolume* fScoringVolume = nullptr;
    std::vector<G4LogicalVolume*> fLayerVolumes;
};

}  // namespace B1

#endif
