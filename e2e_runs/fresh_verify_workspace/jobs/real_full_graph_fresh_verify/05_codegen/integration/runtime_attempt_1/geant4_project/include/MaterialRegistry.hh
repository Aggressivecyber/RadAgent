// MaterialRegistry.hh
// Material registry for Geant4 simulation
// Provides centralized material access for DetectorConstruction and other classes

#ifndef MATERIAL_REGISTRY_HH
#define MATERIAL_REGISTRY_HH

#include "G4Material.hh"
#include "G4NistManager.hh"
#include <map>
#include <string>
#include <vector>

class MaterialRegistry {
public:
    static MaterialRegistry& Instance();
    
    // Get material by material_id from G4ModelIR
    G4Material* GetMaterial(const std::string& material_id) const;
    
    // Initialize registry from G4ModelIR materials
    void Initialize(const std::vector<std::pair<std::string, std::string>>& material_ids);
    
    // Check if material exists
    bool HasMaterial(const std::string& material_id) const;
    
private:
    MaterialRegistry();
    ~MaterialRegistry() = default;
    MaterialRegistry(const MaterialRegistry&) = delete;
    MaterialRegistry& operator=(const MaterialRegistry&) = delete;
    
    // Build material from G4ModelIR specification
    G4Material* BuildMaterial(const std::string& material_id);
    
    std::map<std::string, G4Material*> fMaterialMap;
    G4NistManager* fNistManager;
};

#endif // MATERIAL_REGISTRY_HH