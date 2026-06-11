// MaterialRegistry.cc
// Implementation of MaterialRegistry

#include "MaterialRegistry.hh"
#include "G4SystemOfUnits.hh"
#include "G4String.hh"

MaterialRegistry& MaterialRegistry::Instance() {
    static MaterialRegistry instance;
    return instance;
}

MaterialRegistry::MaterialRegistry() : fNistManager(G4NistManager::Instance()) {
}

void MaterialRegistry::Initialize(const std::vector<std::pair<std::string, std::string>>& material_ids) {
    // material_ids contains pairs of (material_id, nist_name)
    for (const auto& [material_id, nist_name] : material_ids) {
        if (fMaterialMap.find(material_id) == fMaterialMap.end()) {
            G4Material* material = fNistManager->FindOrBuildMaterial(nist_name);
            if (material) {
                fMaterialMap[material_id] = material;
            } else {
                G4Exception("MaterialRegistry::Initialize", "MaterialRegistry001", 
                           FatalException, 
                           ("Could not build material: " + nist_name).c_str());
            }
        }
    }
}

G4Material* MaterialRegistry::GetMaterial(const std::string& material_id) const {
    auto it = fMaterialMap.find(material_id);
    if (it != fMaterialMap.end()) {
        return it->second;
    }
    return nullptr;
}

bool MaterialRegistry::HasMaterial(const std::string& material_id) const {
    return fMaterialMap.find(material_id) != fMaterialMap.end();
}

G4Material* MaterialRegistry::BuildMaterial(const std::string& material_id) {
    // Currently not used as we initialize all materials at once
    // Could be extended for custom materials
    return nullptr;
}