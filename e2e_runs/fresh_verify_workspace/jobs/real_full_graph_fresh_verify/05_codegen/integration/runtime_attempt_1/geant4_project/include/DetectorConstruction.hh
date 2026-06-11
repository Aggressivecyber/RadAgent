// DetectorConstruction.hh
// Constructs detector geometry from G4ModelIR and provides logical volume accessors
// for SensitiveDetector attachment and scoring.

#ifndef DETECTOR_CONSTRUCTION_HH
#define DETECTOR_CONSTRUCTION_HH

#include "G4VUserDetectorConstruction.hh"
#include "G4String.hh"
#include <map>

class G4VPhysicalVolume;
class G4LogicalVolume;

class MaterialRegistry;
class PlacementManager;

class DetectorConstruction : public G4VUserDetectorConstruction
{
public:
    DetectorConstruction();
    ~DetectorConstruction() override;

    DetectorConstruction(const DetectorConstruction&) = delete;
    DetectorConstruction& operator=(const DetectorConstruction&) = delete;

    G4VPhysicalVolume* Construct() override;
    void ConstructSDandField() override;

    // Accessors for downstream modules
    G4LogicalVolume* GetScoringVolume(const G4String& name = "silicon_detector") const;
    MaterialRegistry* GetMaterialRegistry() const;
    PlacementManager* GetPlacementManager() const;

private:
    void DefineMaterials();
    void BuildGeometry();
    void AttachSensitiveDetectors();

    MaterialRegistry* fMaterialRegistry;
    PlacementManager* fPlacementManager;

    std::map<G4String, G4LogicalVolume*> fScoringVolumes;
};

#endif // DETECTOR_CONSTRUCTION_HH
