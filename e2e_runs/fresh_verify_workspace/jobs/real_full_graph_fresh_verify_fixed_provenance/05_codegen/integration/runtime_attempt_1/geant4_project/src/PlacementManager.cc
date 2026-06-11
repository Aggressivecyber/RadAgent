// PlacementManager.cc
// Implementation of PlacementManager

#include "PlacementManager.hh"
#include "G4SystemOfUnits.hh"
#include "G4Box.hh"
#include "G4PVPlacement.hh"
#include "G4RotationMatrix.hh"
#include "G4Exception.hh"

PlacementManager& PlacementManager::Instance() {
    static PlacementManager instance;
    return instance;
}

PlacementManager::PlacementManager() : fWorldVolume(nullptr) {
}

void PlacementManager::Initialize(G4VPhysicalVolume* world_pv) {
    fWorldVolume = world_pv;
    if (!fWorldVolume) {
        G4Exception("PlacementManager::Initialize", "PlacementManager001", 
                   FatalException, 
                   "World physical volume is null");
    }
    
    // Register world volume with component_id "world"
    fPhysicalVolumeMap["world"] = fWorldVolume;
    fLogicalVolumeMap["world"] = fWorldVolume->GetLogicalVolume();
}

G4VPhysicalVolume* PlacementManager::PlaceVolume(const G4String& component_id,
                                                  G4LogicalVolume* logical_volume,
                                                  const G4String& mother_component_id,
                                                  const G4ThreeVector& position,
                                                  G4RotationMatrix* rotation,
                                                  G4bool check_overlaps) {
    // Check if component already placed
    if (fPhysicalVolumeMap.find(component_id) != fPhysicalVolumeMap.end()) {
        G4Exception("PlacementManager::PlaceVolume", "PlacementManager002", 
                   JustWarning, 
                   ("Component " + component_id + " already placed").c_str());
        return fPhysicalVolumeMap[component_id];
    }
    
    // Get mother logical volume
    G4LogicalVolume* mother_logical = nullptr;
    if (mother_component_id.empty() || mother_component_id == "world") {
        mother_logical = fLogicalVolumeMap["world"];
    } else {
        auto it = fLogicalVolumeMap.find(mother_component_id);
        if (it != fLogicalVolumeMap.end()) {
            mother_logical = it->second;
        } else {
            G4Exception("PlacementManager::PlaceVolume", "PlacementManager003", 
                       FatalException, 
                       ("Mother component " + mother_component_id + " not found").c_str());
        }
    }
    
    // Create physical volume
    G4PVPlacement* physical_volume = new G4PVPlacement(
        rotation,
        position,
        logical_volume,
        component_id,
        mother_logical,
        false,           // pMany
        0,               // copyNo
        check_overlaps   // surfCheck
    );
    
    // Store mappings
    fPhysicalVolumeMap[component_id] = physical_volume;
    fLogicalVolumeMap[component_id] = logical_volume;
    
    return physical_volume;
}

G4VPhysicalVolume* PlacementManager::GetPhysicalVolume(const G4String& component_id) const {
    auto it = fPhysicalVolumeMap.find(component_id);
    if (it != fPhysicalVolumeMap.end()) {
        return it->second;
    }
    return nullptr;
}

G4LogicalVolume* PlacementManager::GetLogicalVolume(const G4String& component_id) const {
    auto it = fLogicalVolumeMap.find(component_id);
    if (it != fLogicalVolumeMap.end()) {
        return it->second;
    }
    return nullptr;
}

G4VPhysicalVolume* PlacementManager::GetWorldVolume() const {
    return fWorldVolume;
}