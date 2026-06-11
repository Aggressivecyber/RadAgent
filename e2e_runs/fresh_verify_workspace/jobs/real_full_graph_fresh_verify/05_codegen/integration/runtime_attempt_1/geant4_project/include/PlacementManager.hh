// PlacementManager.hh
// Placement manager for Geant4 simulation
// Manages physical volume placements and provides volume accessors

#ifndef PLACEMENT_MANAGER_HH
#define PLACEMENT_MANAGER_HH

#include "G4VPhysicalVolume.hh"
#include "G4LogicalVolume.hh"
#include "G4PVPlacement.hh"
#include "G4RotationMatrix.hh"
#include "G4ThreeVector.hh"
#include "G4String.hh"
#include <map>
#include <vector>

class PlacementManager {
public:
    static PlacementManager& Instance();
    
    // Initialize with world physical volume
    void Initialize(G4VPhysicalVolume* world_pv);
    
    // Place a volume in the geometry hierarchy
    G4VPhysicalVolume* PlaceVolume(const G4String& component_id,
                                   G4LogicalVolume* logical_volume,
                                   const G4String& mother_component_id,
                                   const G4ThreeVector& position,
                                   G4RotationMatrix* rotation = nullptr,
                                   G4bool check_overlaps = true);
    
    // Get physical volume by component_id
    G4VPhysicalVolume* GetPhysicalVolume(const G4String& component_id) const;
    
    // Get logical volume by component_id
    G4LogicalVolume* GetLogicalVolume(const G4String& component_id) const;
    
    // Get world physical volume
    G4VPhysicalVolume* GetWorldVolume() const;
    
private:
    PlacementManager();
    ~PlacementManager() = default;
    PlacementManager(const PlacementManager&) = delete;
    PlacementManager& operator=(const PlacementManager&) = delete;
    
    // Store mappings
    std::map<std::string, G4VPhysicalVolume*> fPhysicalVolumeMap;
    std::map<std::string, G4LogicalVolume*> fLogicalVolumeMap;
    G4VPhysicalVolume* fWorldVolume;
};

#endif // PLACEMENT_MANAGER_HH