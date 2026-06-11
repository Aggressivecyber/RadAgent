"""Mock model provider — returns deterministic responses for testing."""

from __future__ import annotations

import json
from typing import Any

from agent_core.models.schemas import ModelCallResult, ModelProvider, ModelTask

# ── Material module ─────────────────────────────────────────────────

_MATERIAL_HH = r"""#pragma once

#include "G4Material.hh"
#include "G4Element.hh"
#include "G4Isotope.hh"
#include <map>
#include <string>
#include <vector>

class MaterialRegistry {
public:
    static MaterialRegistry* Instance();

    void RegisterStandardMaterials();
    G4Material* GetMaterial(const G4String& name) const;
    bool HasMaterial(const G4String& name) const;
    void PrintMaterialTable() const;

private:
    MaterialRegistry() = default;
    ~MaterialRegistry() = default;
    static MaterialRegistry* fgInstance;

    void DefineElements();
    void DefineNISTMaterials();
    void DefineCustomMaterials();

    std::map<G4String, G4Material*> fMaterials;
};
"""

_MATERIAL_CC = r"""#include "MaterialRegistry.hh"

#include "G4Material.hh"
#include "G4Element.hh"
#include "G4NistManager.hh"
#include "G4SystemOfUnits.hh"
#include "G4UnitsTable.hh"

#include <iomanip>
#include <iostream>

MaterialRegistry* MaterialRegistry::fgInstance = nullptr;

MaterialRegistry* MaterialRegistry::Instance() {
    if (!fgInstance) {
        fgInstance = new MaterialRegistry();
    }
    return fgInstance;
}

void MaterialRegistry::RegisterStandardMaterials() {
    DefineElements();
    DefineNISTMaterials();
    DefineCustomMaterials();
}

void MaterialRegistry::DefineElements() {
    G4NistManager* nist = G4NistManager::Instance();
    nist->FindOrBuildElement(1);   // H
    nist->FindOrBuildElement(6);   // C
    nist->FindOrBuildElement(7);   // N
    nist->FindOrBuildElement(8);   // O
    nist->FindOrBuildElement(13);  // Al
    nist->FindOrBuildElement(14);  // Si
    nist->FindOrBuildElement(26);  // Fe
    nist->FindOrBuildElement(29);  // Cu
    nist->FindOrBuildElement(74);  // W
    nist->FindOrBuildElement(82);  // Pb
}

void MaterialRegistry::DefineNISTMaterials() {
    G4NistManager* nist = G4NistManager::Instance();

    auto air = nist->FindOrBuildMaterial("G4_AIR");
    fMaterials["Air"] = air;

    auto water = nist->FindOrBuildMaterial("G4_WATER");
    fMaterials["Water"] = water;

    auto lead = nist->FindOrBuildMaterial("G4_Pb");
    fMaterials["Lead"] = lead;

    auto aluminium = nist->FindOrBuildMaterial("G4_Al");
    fMaterials["Aluminium"] = aluminium;

    auto silicon = nist->FindOrBuildMaterial("G4_Si");
    fMaterials["Silicon"] = silicon;

    auto copper = nist->FindOrBuildMaterial("G4_Cu");
    fMaterials["Copper"] = copper;

    auto tungsten = nist->FindOrBuildMaterial("G4_W");
    fMaterials["Tungsten"] = tungsten;
}

void MaterialRegistry::DefineCustomMaterials() {
    G4NistManager* nist = G4NistManager::Instance();

    auto* plastic = new G4Material("PlasticScintillator", 1.032 * g / cm3, 2);
    plastic->AddElement(nist->FindOrBuildElement(1), 8);
    plastic->AddElement(nist->FindOrBuildElement(6), 9);
    fMaterials["PlasticScintillator"] = plastic;

    auto* crystal = new G4Material("NaI", 3.67 * g / cm3, 2);
    crystal->AddElement(nist->FindOrBuildElement(11), 1);
    crystal->AddElement(nist->FindOrBuildElement(53), 1);
    fMaterials["NaI"] = crystal;
}

G4Material* MaterialRegistry::GetMaterial(const G4String& name) const {
    auto it = fMaterials.find(name);
    if (it != fMaterials.end()) {
        return it->second;
    }
    return nullptr;
}

bool MaterialRegistry::HasMaterial(const G4String& name) const {
    return fMaterials.find(name) != fMaterials.end();
}

void MaterialRegistry::PrintMaterialTable() const {
    G4cout << "\n=== Registered Materials ===" << G4endl;
    for (const auto& [name, mat] : fMaterials) {
        G4cout << "  " << std::setw(24) << name
               << "  density = " << std::setprecision(3)
               << G4BestUnit(mat->GetDensity(), "Volumic Mass")
               << G4endl;
    }
    G4cout << G4endl;
}
"""


# ── Geometry module ──────────────────────────────────────────────────

_GEOMETRY_HH = r"""#pragma once

#include "G4VUserDetectorConstruction.hh"
#include "G4LogicalVolume.hh"
#include "G4VPhysicalVolume.hh"
#include "G4Material.hh"
#include <vector>

class DetectorConstruction : public G4VUserDetectorConstruction {
public:
    DetectorConstruction();
    ~DetectorConstruction() override = default;

    G4VPhysicalVolume* Construct() override;
    void ConstructSDandField() override;

    G4LogicalVolume* GetWorldLogicalVolume() const { return fWorldLV; }
    G4double GetWorldSizeXY() const { return fWorldSizeXY; }
    G4double GetWorldSizeZ() const { return fWorldSizeZ; }

private:
    G4LogicalVolume* fWorldLV = nullptr;
    G4LogicalVolume* fTargetLV = nullptr;
    G4LogicalVolume* fDetectorLV = nullptr;

    G4double fWorldSizeXY = 10.0 * m;
    G4double fWorldSizeZ = 10.0 * m;
    G4double fTargetThickness = 1.0 * cm;
    G4double fDetectorDistance = 50.0 * cm;
    G4double fDetectorSizeXY = 20.0 * cm;
    G4double fDetectorThickness = 5.0 * cm;

    void DefineDimensions();
    G4VPhysicalVolume* BuildWorld();
    G4LogicalVolume* BuildTarget();
    G4LogicalVolume* BuildDetector();
};
"""

_GEOMETRY_CC = r"""#include "DetectorConstruction.hh"

#include "MaterialRegistry.hh"
#include "SensitiveDetector.hh"

#include "G4Box.hh"
#include "G4LogicalVolume.hh"
#include "G4PVPlacement.hh"
#include "G4SystemOfUnits.hh"
#include "G4NistManager.hh"
#include "G4SDManager.hh"
#include "G4VSensitiveDetector.hh"
#include "G4FieldManager.hh"
#include "G4TransportationManager.hh"

DetectorConstruction::DetectorConstruction() {
    DefineDimensions();
}

void DetectorConstruction::DefineDimensions() {
    fWorldSizeXY = 2.0 * m;
    fWorldSizeZ = 2.0 * m;
    fTargetThickness = 1.0 * cm;
    fDetectorDistance = 50.0 * cm;
    fDetectorSizeXY = 20.0 * cm;
    fDetectorThickness = 5.0 * cm;
}

G4VPhysicalVolume* DetectorConstruction::Construct() {
    auto* matReg = MaterialRegistry::Instance();
    matReg->RegisterStandardMaterials();

    auto* worldPV = BuildWorld();
    BuildTarget();
    BuildDetector();

    return worldPV;
}

G4VPhysicalVolume* DetectorConstruction::BuildWorld() {
    auto* matReg = MaterialRegistry::Instance();
    auto* worldSolid = new G4Box("WorldBox",
                                  fWorldSizeXY / 2.0,
                                  fWorldSizeXY / 2.0,
                                  fWorldSizeZ / 2.0);
    fWorldLV = new G4LogicalVolume(worldSolid,
                                    matReg->GetMaterial("Air"),
                                    "WorldLV");
    auto* worldPV = new G4PVPlacement(nullptr,
                                       G4ThreeVector(),
                                       fWorldLV,
                                       "WorldPV",
                                       nullptr,
                                       false,
                                       0);
    return worldPV;
}

G4LogicalVolume* DetectorConstruction::BuildTarget() {
    auto* matReg = MaterialRegistry::Instance();
    auto* targetSolid = new G4Box("TargetBox",
                                   5.0 * cm,
                                   5.0 * cm,
                                   fTargetThickness / 2.0);
    fTargetLV = new G4LogicalVolume(targetSolid,
                                     matReg->GetMaterial("Lead"),
                                     "TargetLV");
    new G4PVPlacement(nullptr,
                      G4ThreeVector(0.0, 0.0, -20.0 * cm),
                      fTargetLV,
                      "TargetPV",
                      fWorldLV,
                      false,
                      0);
    return fTargetLV;
}

G4LogicalVolume* DetectorConstruction::BuildDetector() {
    auto* matReg = MaterialRegistry::Instance();
    auto* detSolid = new G4Box("DetectorBox",
                                fDetectorSizeXY / 2.0,
                                fDetectorSizeXY / 2.0,
                                fDetectorThickness / 2.0);
    fDetectorLV = new G4LogicalVolume(detSolid,
                                       matReg->GetMaterial("NaI"),
                                       "DetectorLV");
    new G4PVPlacement(nullptr,
                      G4ThreeVector(0.0, 0.0, fDetectorDistance),
                      fDetectorLV,
                      "DetectorPV",
                      fWorldLV,
                      false,
                      0);
    return fDetectorLV;
}

void DetectorConstruction::ConstructSDandField() {
    auto* sdManager = G4SDManager::GetSDMpointer();
    auto* sd = new SensitiveDetector("DetectorSD", "DetectorHitsCollection");
    sdManager->AddNewDetector(sd);
    fDetectorLV->SetSensitiveDetector(sd);
}
"""


# ── Placement module ─────────────────────────────────────────────────

_PLACEMENT_HH = r"""#pragma once

#include "G4ThreeVector.hh"
#include "G4RotationMatrix.hh"
#include "G4LogicalVolume.hh"
#include "G4VPhysicalVolume.hh"
#include <map>
#include <string>
#include <vector>

struct PlacementInfo {
    G4String name;
    G4ThreeVector translation;
    G4RotationMatrix rotation;
    G4LogicalVolume* logicalVolume = nullptr;
    G4VPhysicalVolume* physicalVolume = nullptr;
    G4int copyNumber = 0;
};

class PlacementManager {
public:
    static PlacementManager* Instance();

    void PlaceVolume(const G4String& name,
                     G4LogicalVolume* logicalVolume,
                     G4LogicalVolume* motherLogical,
                     const G4ThreeVector& translation,
                     const G4RotationMatrix* rotation = nullptr,
                     G4int copyNumber = 0);

    void PlaceRepeated(const G4String& baseName,
                       G4LogicalVolume* logicalVolume,
                       G4LogicalVolume* motherLogical,
                       const G4ThreeVector& startPosition,
                       const G4ThreeVector& offset,
                       G4int count);

    PlacementInfo* GetPlacement(const G4String& name);
    G4int GetTotalPlacements() const { return fPlacements.size(); }
    void PrintPlacementSummary() const;

private:
    PlacementManager() = default;
    ~PlacementManager() = default;
    static PlacementManager* fgInstance;

    std::map<G4String, PlacementInfo> fPlacements;
    G4int fCopyCounter = 0;
};
"""

_PLACEMENT_CC = r"""#include "PlacementManager.hh"

#include "G4PVPlacement.hh"
#include "G4PVReplica.hh"
#include "G4LogicalVolume.hh"
#include "G4SystemOfUnits.hh"

#include <iomanip>
#include <iostream>

PlacementManager* PlacementManager::fgInstance = nullptr;

PlacementManager* PlacementManager::Instance() {
    if (!fgInstance) {
        fgInstance = new PlacementManager();
    }
    return fgInstance;
}

void PlacementManager::PlaceVolume(
    const G4String& name,
    G4LogicalVolume* logicalVolume,
    G4LogicalVolume* motherLogical,
    const G4ThreeVector& translation,
    const G4RotationMatrix* rotation,
    G4int copyNumber) {

    auto* physVol = new G4PVPlacement(
        rotation,
        translation,
        logicalVolume,
        name,
        motherLogical,
        false,
        copyNumber);

    PlacementInfo info;
    info.name = name;
    info.translation = translation;
    if (rotation) {
        info.rotation = *rotation;
    }
    info.logicalVolume = logicalVolume;
    info.physicalVolume = physVol;
    info.copyNumber = copyNumber;

    fPlacements[name] = info;
}

void PlacementManager::PlaceRepeated(
    const G4String& baseName,
    G4LogicalVolume* logicalVolume,
    G4LogicalVolume* motherLogical,
    const G4ThreeVector& startPosition,
    const G4ThreeVector& offset,
    G4int count) {

    for (G4int i = 0; i < count; ++i) {
        G4String volName = baseName + "_" + std::to_string(i);
        G4ThreeVector pos = startPosition + i * offset;
        PlaceVolume(volName, logicalVolume, motherLogical, pos, nullptr, i);
    }
}

PlacementInfo* PlacementManager::GetPlacement(const G4String& name) {
    auto it = fPlacements.find(name);
    if (it != fPlacements.end()) {
        return &(it->second);
    }
    return nullptr;
}

void PlacementManager::PrintPlacementSummary() const {
    G4cout << "\n=== Volume Placements ===" << G4endl;
    for (const auto& [name, info] : fPlacements) {
        G4cout << "  " << std::setw(24) << name
               << " at ("
               << std::setprecision(1)
               << info.translation.x() / cm << ", "
               << info.translation.y() / cm << ", "
               << info.translation.z() / cm
               << ") cm" << G4endl;
    }
    G4cout << "  Total: " << fPlacements.size() << " placements" << G4endl;
}
"""


# ── Source module ─────────────────────────────────────────────────────

_SOURCE_HH = r"""#pragma once

#include "G4VUserPrimaryGeneratorAction.hh"
#include "G4ParticleGun.hh"
#include "G4ThreeVector.hh"

class G4Event;

class PrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction {
public:
    PrimaryGeneratorAction();
    ~PrimaryGeneratorAction() override;

    void GeneratePrimaries(G4Event* event) override;

    void SetParticleEnergy(G4double energy);
    void SetParticlePosition(const G4ThreeVector& pos);
    void SetParticleDirection(const G4ThreeVector& dir);
    void SetParticleType(const G4String& particleName);

    G4ParticleGun* GetParticleGun() const { return fParticleGun; }

private:
    G4ParticleGun* fParticleGun = nullptr;
    G4double fKineticEnergy = 1.0 * GeV;
    G4ThreeVector fStartPosition;
    G4ThreeVector fStartDirection;

    void ConfigureDefaultBeam();
};
"""

_SOURCE_CC = r"""#include "PrimaryGeneratorAction.hh"

#include "G4ParticleGun.hh"
#include "G4ParticleDefinition.hh"
#include "G4ParticleTable.hh"
#include "G4SystemOfUnits.hh"
#include "G4Electron.hh"
#include "G4Gamma.hh"
#include "G4Proton.hh"
#include "G4Event.hh"

PrimaryGeneratorAction::PrimaryGeneratorAction()
    : G4VUserPrimaryGeneratorAction() {
    fParticleGun = new G4ParticleGun(1);
    fStartPosition = G4ThreeVector(0.0, 0.0, -80.0 * cm);
    fStartDirection = G4ThreeVector(0.0, 0.0, 1.0);
    ConfigureDefaultBeam();
}

PrimaryGeneratorAction::~PrimaryGeneratorAction() {
    delete fParticleGun;
}

void PrimaryGeneratorAction::ConfigureDefaultBeam() {
    auto* particleTable = G4ParticleTable::GetParticleTable();
    auto* gamma = particleTable->FindParticle("gamma");
    fParticleGun->SetParticleDefinition(gamma);
    fParticleGun->SetParticleEnergy(fKineticEnergy);
    fParticleGun->SetParticlePosition(fStartPosition);
    fParticleGun->SetParticleMomentumDirection(fStartDirection);
}

void PrimaryGeneratorAction::GeneratePrimaries(G4Event* event) {
    fParticleGun->GeneratePrimaryVertex(event);
}

void PrimaryGeneratorAction::SetParticleEnergy(G4double energy) {
    fKineticEnergy = energy;
    fParticleGun->SetParticleEnergy(energy);
}

void PrimaryGeneratorAction::SetParticlePosition(const G4ThreeVector& pos) {
    fStartPosition = pos;
    fParticleGun->SetParticlePosition(pos);
}

void PrimaryGeneratorAction::SetParticleDirection(const G4ThreeVector& dir) {
    fStartDirection = dir.unit();
    fParticleGun->SetParticleMomentumDirection(fStartDirection);
}

void PrimaryGeneratorAction::SetParticleType(const G4String& particleName) {
    auto* particleTable = G4ParticleTable::GetParticleTable();
    auto* particle = particleTable->FindParticle(particleName);
    if (particle) {
        fParticleGun->SetParticleDefinition(particle);
    }
}
"""


# ── Physics module ────────────────────────────────────────────────────

_PHYSICS_HH = r"""#pragma once

#include "G4VModularPhysicsList.hh"
#include "G4VPhysicsConstructor.hh"
#include <vector>

class PhysicsListFactoryWrapper {
public:
    static G4VModularPhysicsList* CreatePhysicsList(const G4String& preset = "standard");
    static std::vector<G4String> GetAvailablePresets();

private:
    static void RegisterEMPhysics(G4VModularPhysicsList* list, const G4String& emOption);
    static void RegisterHadronicPhysics(G4VModularPhysicsList* list);
    static void RegisterDecayPhysics(G4VVModularPhysicsList* list);
    static void SetProductionCuts(G4VModularPhysicsList* list);
};
"""

_PHYSICS_CC = r"""#include "PhysicsListFactoryWrapper.hh"

#include "G4VModularPhysicsList.hh"
#include "G4EmStandardPhysics.hh"
#include "G4EmStandardPhysicsOption3.hh"
#include "G4EmStandardPhysicsOption4.hh"
#include "G4EmLivermorePhysics.hh"
#include "G4EmPenelopePhysics.hh"
#include "G4HadronElasticPhysics.hh"
#include "G4HadronPhysicsFTFP_BERT.hh"
#include "G4DecayPhysics.hh"
#include "G4OpticalPhysics.hh"
#include "G4SystemOfUnits.hh"
#include "G4ProductionCuts.hh"

std::vector<G4String> PhysicsListFactoryWrapper::GetAvailablePresets() {
    return {"standard", "em_lowenergy", "em_penelope", "hadronic", "full"};
}

G4VModularPhysicsList* PhysicsListFactoryWrapper::CreatePhysicsList(const G4String& preset) {
    auto* physicsList = new G4VModularPhysicsList();

    if (preset == "standard") {
        RegisterEMPhysics(physicsList, "standard");
        RegisterDecayPhysics(physicsList);
    } else if (preset == "em_lowenergy") {
        RegisterEMPhysics(physicsList, "livermore");
        RegisterDecayPhysics(physicsList);
    } else if (preset == "em_penelope") {
        RegisterEMPhysics(physicsList, "penelope");
        RegisterDecayPhysics(physicsList);
    } else if (preset == "hadronic") {
        RegisterEMPhysics(physicsList, "option4");
        RegisterHadronicPhysics(physicsList);
        RegisterDecayPhysics(physicsList);
    } else if (preset == "full") {
        RegisterEMPhysics(physicsList, "option4");
        RegisterHadronicPhysics(physicsList);
        RegisterDecayPhysics(physicsList);
    }

    SetProductionCuts(physicsList);
    return physicsList;
}

void PhysicsListFactoryWrapper::RegisterEMPhysics(
    G4VModularPhysicsList* list, const G4String& emOption) {
    if (emOption == "standard") {
        list->RegisterPhysics(new G4EmStandardPhysics());
    } else if (emOption == "option3") {
        list->RegisterPhysics(new G4EmStandardPhysicsOption3());
    } else if (emOption == "option4") {
        list->RegisterPhysics(new G4EmStandardPhysicsOption4());
    } else if (emOption == "livermore") {
        list->RegisterPhysics(new G4EmLivermorePhysics());
    } else if (emOption == "penelope") {
        list->RegisterPhysics(new G4EmPenelopePhysics());
    }
}

void PhysicsListFactoryWrapper::RegisterHadronicPhysics(
    G4VModularPhysicsList* list) {
    list->RegisterPhysics(new G4HadronElasticPhysics());
    list->RegisterPhysics(new G4HadronPhysicsFTFP_BERT());
}

void PhysicsListFactoryWrapper::RegisterDecayPhysics(
    G4VModularPhysicsList* list) {
    list->RegisterPhysics(new G4DecayPhysics());
}

void PhysicsListFactoryWrapper::SetProductionCuts(
    G4VModularPhysicsList* list) {
    G4double defaultCut = 1.0 * mm;
    list->SetDefaultCutValue(defaultCut);
    list->SetCutValue(defaultCut, "gamma");
    list->SetCutValue(defaultCut, "e-");
    list->SetCutValue(defaultCut, "e+");
    list->SetCutValue(defaultCut, "proton");
}
"""

_PHYSICS_MAC = r"""# run.mac — Physics configuration macro
# RadAgent generated physics list configuration

/run/initialize

# Production cuts (default 1 mm)
/run/setCut 1 mm

# EM physics options
/process/em/fluo true
/process/em/pixe true
/process/em/deexcitationIgnoreCut false

# Step limits
/process/maxStepSize 1 mm

# Verbosity
/process/em/verbose 0
"""


# ── Sensitive Detector module ────────────────────────────────────────

_SD_HH = r"""#pragma once

#include "G4VSensitiveDetector.hh"
#include "G4Step.hh"
#include "G4HCofThisEvent.hh"
#include "G4TouchableHistory.hh"
#include <vector>

struct HitData {
    G4double energyDeposit = 0.0;
    G4double kineticEnergy = 0.0;
    G4ThreeVector position;
    G4ThreeVector momentumDirection;
    G4double time = 0.0;
    G4String particleName;
    G4int trackID = 0;
    G4int parentID = 0;
    G4int copyNumber = 0;
};

class SensitiveDetector : public G4VSensitiveDetector {
public:
    SensitiveDetector(const G4String& name,
                      const G4String& hitsCollectionName);
    ~SensitiveDetector() override = default;

    void Initialize(G4HCofThisEvent* hitCollection) override;
    G4bool ProcessHits(G4Step* step, G4TouchableHistory* history) override;
    void EndOfEvent(G4HCofThisEvent* hitCollection) override;

    const std::vector<HitData>& GetHits() const { return fHits; }
    G4int GetNumberOfHits() const { return fHits.size(); }
    void ClearHits();

private:
    std::vector<HitData> fHits;
    G4double fTotalEnergyDeposit = 0.0;
};
"""

_SD_CC = r"""#include "SensitiveDetector.hh"

#include "G4Step.hh"
#include "G4Track.hh"
#include "G4ParticleDefinition.hh"
#include "G4HCofThisEvent.hh"
#include "G4TouchableHistory.hh"
#include "G4SystemOfUnits.hh"
#include "G4VPhysicalVolume.hh"
#include "G4LogicalVolume.hh"

#include <algorithm>

SensitiveDetector::SensitiveDetector(
    const G4String& name,
    const G4String& hitsCollectionName)
    : G4VSensitiveDetector(name) {
    collectionName.push_back(hitsCollectionName);
}

void SensitiveDetector::Initialize(G4HCofThisEvent* hitCollection) {
    fHits.clear();
    fTotalEnergyDeposit = 0.0;
}

G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory* history) {
    G4double edep = step->GetTotalEnergyDeposit();
    if (edep <= 0.0) {
        return false;
    }

    HitData hit;
    hit.energyDeposit = edep;
    hit.kineticEnergy = step->GetPreStepPoint()->GetKineticEnergy();
    hit.position = step->GetPreStepPoint()->GetPosition();
    hit.momentumDirection = step->GetPreStepPoint()->GetMomentumDirection();
    hit.time = step->GetPreStepPoint()->GetGlobalTime();

    auto* track = step->GetTrack();
    hit.particleName = track->GetParticleDefinition()->GetParticleName();
    hit.trackID = track->GetTrackID();
    hit.parentID = track->GetParentID();

    auto* touchable = step->GetPreStepPoint()->GetTouchable();
    hit.copyNumber = touchable->GetVolume()->GetCopyNo();

    fHits.push_back(hit);
    fTotalEnergyDeposit += edep;

    return true;
}

void SensitiveDetector::EndOfEvent(G4HCofThisEvent* hitCollection) {
}

void SensitiveDetector::ClearHits() {
    fHits.clear();
    fTotalEnergyDeposit = 0.0;
}
"""


# ── Scoring module ───────────────────────────────────────────────────

_SCORING_HH = r"""#pragma once

#include "G4THitsMap.hh"
#include <map>
#include <string>
#include <vector>

struct ScoringResult {
    G4String name;
    G4double value = 0.0;
    G4String unit;
    G4double error = 0.0;
    G4int numberOfEntries = 0;
};

class ScoringManager {
public:
    static ScoringManager* Instance();

    void RegisterScorer(const G4String& name, const G4String& unit = "");
    void FillScorer(const G4String& name, G4int index, G4double value, G4double weight = 1.0);
    ScoringResult GetResult(const G4String& name) const;
    std::vector<ScoringResult> GetAllResults() const;
    void ResetAll();
    void PrintResults() const;

private:
    ScoringManager() = default;
    ~ScoringManager() = default;
    static ScoringManager* fgInstance;

    struct ScorerData {
        G4String name;
        G4String unit;
        std::map<G4int, G4double> sums;
        std::map<G4int, G4double> sumsSquared;
        std::map<G4int, G4int> counts;
    };

    std::map<G4String, ScorerData> fScorers;
};
"""

_SCORING_CC = r"""#include "ScoringManager.hh"

#include "G4SystemOfUnits.hh"

#include <cmath>
#include <iomanip>
#include <iostream>

ScoringManager* ScoringManager::fgInstance = nullptr;

ScoringManager* ScoringManager::Instance() {
    if (!fgInstance) {
        fgInstance = new ScoringManager();
    }
    return fgInstance;
}

void ScoringManager::RegisterScorer(const G4String& name, const G4String& unit) {
    ScorerData data;
    data.name = name;
    data.unit = unit;
    fScorers[name] = data;
}

void ScoringManager::FillScorer(const G4String& name, G4int index,
                                  G4double value, G4double weight) {
    auto it = fScorers.find(name);
    if (it == fScorers.end()) {
        RegisterScorer(name);
    }
    auto& scorer = fScorers[name];
    scorer.sums[index] += value * weight;
    scorer.sumsSquared[index] += (value * weight) * (value * weight);
    scorer.counts[index]++;
}

ScoringResult ScoringManager::GetResult(const G4String& name) const {
    ScoringResult result;
    result.name = name;

    auto it = fScorers.find(name);
    if (it == fScorers.end()) {
        return result;
    }

    const auto& scorer = it->second;
    G4double totalSum = 0.0;
    G4double totalSumSq = 0.0;
    G4int totalCount = 0;

    for (const auto& [idx, sum] : scorer.sums) {
        totalSum += sum;
        totalSumSq += scorer.sumsSquared.at(idx);
        totalCount += scorer.counts.at(idx);
    }

    result.value = totalSum;
    result.unit = scorer.unit;
    result.numberOfEntries = totalCount;

    if (totalCount > 1) {
        result.error = std::sqrt(totalSumSq / totalCount
                                  - (totalSum / totalCount) * (totalSum / totalCount));
    }

    return result;
}

std::vector<ScoringResult> ScoringManager::GetAllResults() const {
    std::vector<ScoringResult> results;
    for (const auto& [name, _] : fScorers) {
        results.push_back(GetResult(name));
    }
    return results;
}

void ScoringManager::ResetAll() {
    for (auto& [name, scorer] : fScorers) {
        scorer.sums.clear();
        scorer.sumsSquared.clear();
        scorer.counts.clear();
    }
}

void ScoringManager::PrintResults() const {
    G4cout << "\n=== Scoring Results ===" << G4endl;
    for (const auto& result : GetAllResults()) {
        G4cout << "  " << std::setw(24) << result.name
               << " = " << std::setprecision(6) << result.value
               << " " << result.unit
               << " (" << result.numberOfEntries << " entries)"
               << G4endl;
    }
}
"""


# ── Output Manager module ────────────────────────────────────────────

_OUTPUT_HH = r"""#pragma once

#include <string>
#include <vector>
#include <map>

struct OutputEvent {
    G4int eventID = 0;
    G4double totalEnergyDeposit = 0.0;
    G4int numberOfHits = 0;
    std::map<G4String, G4double> detectorDeposits;
};

class OutputManager {
public:
    static OutputManager* Instance();

    void BeginRun();
    void BeginEvent(G4int eventID);
    void EndEvent();
    void EndRun();
    void RecordHit(const G4String& detectorName, G4double energyDeposit);
    void SetOutputPath(const G4String& path);
    void SetOutputFormat(const G4String& format);

    void WriteResults();
    void ClearEventData();

    const std::vector<OutputEvent>& GetEvents() const { return fEvents; }

private:
    OutputManager() = default;
    ~OutputManager() = default;
    static OutputManager* fgInstance;

    G4String fOutputPath = "./output";
    G4String fOutputFormat = "csv";
    OutputEvent fCurrentEvent;
    std::vector<OutputEvent> fEvents;

    void WriteCSV() const;
    void WriteROOT() const;
};
"""

_OUTPUT_CC = r"""#include "OutputManager.hh"

#include "G4SystemOfUnits.hh"

#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>

OutputManager* OutputManager::fgInstance = nullptr;

OutputManager* OutputManager::Instance() {
    if (!fgInstance) {
        fgInstance = new OutputManager();
    }
    return fgInstance;
}

void OutputManager::BeginRun() {
    fEvents.clear();
}

void OutputManager::BeginEvent(G4int eventID) {
    fCurrentEvent = OutputEvent();
    fCurrentEvent.eventID = eventID;
}

void OutputManager::EndEvent() {
    fCurrentEvent.numberOfHits = 0;
    for (const auto& [det, edep] : fCurrentEvent.detectorDeposits) {
        fCurrentEvent.totalEnergyDeposit += edep;
        fCurrentEvent.numberOfHits++;
    }
    fEvents.push_back(fCurrentEvent);
}

void OutputManager::EndRun() {
    WriteResults();
}

void OutputManager::RecordHit(const G4String& detectorName, G4double energyDeposit) {
    fCurrentEvent.detectorDeposits[detectorName] += energyDeposit;
}

void OutputManager::SetOutputPath(const G4String& path) {
    fOutputPath = path;
}

void OutputManager::SetOutputFormat(const G4String& format) {
    fOutputFormat = format;
}

void OutputManager::ClearEventData() {
    fCurrentEvent = OutputEvent();
}

void OutputManager::WriteResults() {
    if (fOutputFormat == "csv") {
        WriteCSV();
    } else if (fOutputFormat == "root") {
        WriteROOT();
    }
}

void OutputManager::WriteCSV() const {
    std::ofstream file(fOutputPath + "/results.csv");
    if (!file.is_open()) {
        G4cerr << "ERROR: Cannot open output file: "
               << fOutputPath << "/results.csv" << G4endl;
        return;
    }

    file << "event_id,total_edep_MeV,n_hits";
    if (!fEvents.empty()) {
        for (const auto& [det, _] : fEvents[0].detectorDeposits) {
            file << "," << det << "_edep_MeV";
        }
    }
    file << "\n";

    for (const auto& event : fEvents) {
        file << event.eventID << ","
             << std::setprecision(6) << event.totalEnergyDeposit / MeV << ","
             << event.numberOfHits;
        for (const auto& [det, edep] : event.detectorDeposits) {
            file << "," << std::setprecision(6) << edep / MeV;
        }
        file << "\n";
    }
    file.close();
    G4cout << "Results written to " << fOutputPath << "/results.csv" << G4endl;
}

void OutputManager::WriteROOT() const {
    G4cout << "ROOT output configured but TFile writing requires ROOT linkage."
           << G4endl;
}
"""


# ── Action Initialization module ──────────────────────────────────────

_ACTION_INIT_HH = r"""#pragma once

#include "G4VUserActionInitialization.hh"

class DetectorConstruction;
class PrimaryGeneratorAction;
class RunAction;
class EventAction;
class SteppingAction;

class ActionInitialization : public G4VUserActionInitialization {
public:
    explicit ActionInitialization(DetectorConstruction* detConstruction);
    ~ActionInitialization() override = default;

    void Build() override;
    void BuildForMaster() override;

private:
    DetectorConstruction* fDetConstruction = nullptr;
};
"""

_ACTION_INIT_CC = r"""#include "ActionInitialization.hh"
#include "DetectorConstruction.hh"
#include "PrimaryGeneratorAction.hh"
#include "RunAction.hh"
#include "EventAction.hh"
#include "SteppingAction.hh"

ActionInitialization::ActionInitialization(
    DetectorConstruction* detConstruction)
    : G4VUserActionInitialization()
    , fDetConstruction(detConstruction) {
}

void ActionInitialization::Build() {
    SetUserAction(new PrimaryGeneratorAction());

    auto* runAction = new RunAction();
    SetUserAction(runAction);

    auto* eventAction = new EventAction(runAction);
    SetUserAction(eventAction);

    SetUserAction(new SteppingAction(eventAction));
}

void ActionInitialization::BuildForMaster() const {
    SetUserAction(new RunAction());
}
"""

_RUN_ACTION_HH = r"""#pragma once

#include "G4UserRunAction.hh"
#include "G4Run.hh"

class RunAction : public G4UserRunAction {
public:
    RunAction();
    ~RunAction() override = default;

    void BeginOfRunAction(const G4Run* run) override;
    void EndOfRunAction(const G4Run* run) override;

    G4int GetNumberOfEvents() const { return fNumberOfEvents; }
    G4double GetTotalEnergy() const { return fTotalEnergy; }

    void AddEnergyDeposit(G4double edep);
    void SetNumberOfEvents(G4int n);

private:
    G4int fNumberOfEvents = 0;
    G4double fTotalEnergy = 0.0;
    G4double fStartTime = 0.0;
};
"""

_RUN_ACTION_CC = r"""#include "RunAction.hh"

#include "G4Run.hh"
#include "G4SystemOfUnits.hh"
#include "G4Timer.hh"

#include <iomanip>
#include <iostream>

RunAction::RunAction()
    : G4UserRunAction() {
}

void RunAction::BeginOfRunAction(const G4Run* run) {
    fNumberOfEvents = run->GetNumberOfEventsToBeProcessed();
    fTotalEnergy = 0.0;
    G4cout << "### Run " << run->GetRunID()
           << " start (" << fNumberOfEvents << " events) ###" << G4endl;
}

void RunAction::EndOfRunAction(const G4Run* run) {
    G4int nEvents = run->GetNumberOfEvent();
    if (nEvents == 0) {
        return;
    }

    G4cout << "\n### Run " << run->GetRunID() << " end ###" << G4endl;
    G4cout << "  Total events processed: " << nEvents << G4endl;
    G4cout << "  Total energy deposit:   "
           << std::setprecision(6) << fTotalEnergy / MeV
           << " MeV" << G4endl;
    G4cout << "  Average per event:      "
           << std::setprecision(6) << (fTotalEnergy / nEvents) / MeV
           << " MeV" << G4endl;
}

void RunAction::AddEnergyDeposit(G4double edep) {
    fTotalEnergy += edep;
}

void RunAction::SetNumberOfEvents(G4int n) {
    fNumberOfEvents = n;
}
"""

_EVENT_ACTION_HH = r"""#pragma once

#include "G4UserEventAction.hh"

class RunAction;
class G4Event;

class EventAction : public G4UserEventAction {
public:
    explicit EventAction(RunAction* runAction);
    ~EventAction() override = default;

    void BeginOfEventAction(const G4Event* event) override;
    void EndOfEventAction(const G4Event* event) override;

    void AddEnergyDeposit(G4double edep);
    void AddHit();

private:
    RunAction* fRunAction = nullptr;
    G4double fEventEnergyDeposit = 0.0;
    G4int fEventHits = 0;
};
"""

_EVENT_ACTION_CC = r"""#include "EventAction.hh"
#include "RunAction.hh"

#include "G4Event.hh"
#include "G4SystemOfUnits.hh"

#include <iomanip>
#include <iostream>

EventAction::EventAction(RunAction* runAction)
    : G4UserEventAction()
    , fRunAction(runAction) {
}

void EventAction::BeginOfEventAction(const G4Event* event) {
    fEventEnergyDeposit = 0.0;
    fEventHits = 0;
}

void EventAction::EndOfEventAction(const G4Event* event) {
    fRunAction->AddEnergyDeposit(fEventEnergyDeposit);

    if (fEventEnergyDeposit > 0.0) {
        G4int eventID = event->GetEventID();
        if (eventID % 100 == 0) {
            G4cout << "  Event " << std::setw(6) << eventID
                   << " : Edep = " << std::setprecision(4)
                   << fEventEnergyDeposit / MeV << " MeV"
                   << " (" << fEventHits << " hits)" << G4endl;
        }
    }
}

void EventAction::AddEnergyDeposit(G4double edep) {
    fEventEnergyDeposit += edep;
}

void EventAction::AddHit() {
    fEventHits++;
}
"""

_STEPPING_ACTION_HH = r"""#pragma once

#include "G4UserSteppingAction.hh"

class EventAction;
class G4Step;

class SteppingAction : public G4UserSteppingAction {
public:
    explicit SteppingAction(EventAction* eventAction);
    ~SteppingAction() override = default;

    void UserSteppingAction(const G4Step* step) override;

private:
    EventAction* fEventAction = nullptr;
};
"""

_STEPPING_ACTION_CC = r"""#include "SteppingAction.hh"
#include "EventAction.hh"

#include "G4Step.hh"
#include "G4Track.hh"
#include "G4SystemOfUnits.hh"
#include "G4LogicalVolume.hh"
#include "G4VPhysicalVolume.hh"

SteppingAction::SteppingAction(EventAction* eventAction)
    : G4UserSteppingAction()
    , fEventAction(eventAction) {
}

void SteppingAction::UserSteppingAction(const G4Step* step) {
    G4double edep = step->GetTotalEnergyDeposit();
    if (edep <= 0.0) {
        return;
    }

    auto* preStepPoint = step->GetPreStepPoint();
    auto* physicalVolume = preStepPoint->GetPhysicalVolume();
    if (!physicalVolume) {
        return;
    }

    G4String volumeName = physicalVolume->GetName();
    if (volumeName.contains("Detector")) {
        fEventAction->AddEnergyDeposit(edep);
        fEventAction->AddHit();
    }
}
"""


# ── Main / CMake module ──────────────────────────────────────────────

_MAIN_CC = r"""#include "DetectorConstruction.hh"
#include "PhysicsListFactoryWrapper.hh"
#include "ActionInitialization.hh"
#include "PrimaryGeneratorAction.hh"

#include "G4RunManagerFactory.hh"
#include "G4UImanager.hh"
#include "G4VisExecutive.hh"
#include "G4UIExecutive.hh"

#include <iostream>
#include <string>

int main(int argc, char** argv) {
    auto* runManager = G4RunManagerFactory::CreateRunManager(
        G4RunManagerType::Serial);

    auto* detector = new DetectorConstruction();
    runManager->SetUserInitialization(detector);

    auto* physicsList = PhysicsListFactoryWrapper::CreatePhysicsList("standard");
    runManager->SetUserInitialization(physicsList);

    auto* actionInit = new ActionInitialization(detector);
    runManager->SetUserInitialization(actionInit);

    runManager->Initialize();

    auto* uiManager = G4UImanager::GetUIpointer();

    if (argc > 1) {
        G4String macroFile = argv[1];
        G4String command = "/control/execute " + macroFile;
        uiManager->ApplyCommand(command);
    } else {
        G4String command = "/control/execute macros/run.mac";
        uiManager->ApplyCommand(command);
    }

    delete runManager;
    return 0;
}
"""

_CMAKELISTS = r"""cmake_minimum_required(VERSION 3.16)
project(RadAgentSimulation)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Geant4 REQUIRED)

include(${Geant4_USE_FILE})

file(GLOB SOURCES src/*.cc)
file(GLOB HEADERS include/*.hh)

add_executable(radagent_sim main.cc ${SOURCES})

target_include_directories(radagent_sim PRIVATE
    ${CMAKE_SOURCE_DIR}/include
    ${Geant4_INCLUDE_DIRS}
)

target_link_libraries(radagent_sim
    ${Geant4_LIBRARIES}
)

file(COPY macros DESTINATION ${CMAKE_BINARY_DIR})
"""

_RUN_MAC = r"""# run.mac — Default run macro for RadAgent simulation
# RadAgent generated configuration

# Initialize geometry and physics
/control/execute macros/init.mac

# Run configuration
/run/numberOfThreads 1

# Beam configuration
/gun/particle gamma
/gun/energy 1 GeV

# Run 1000 events
/run/beamOn 1000
"""

_INIT_MAC = r"""# init.mac — Initialization macro for RadAgent simulation
# RadAgent generated configuration

# Verbose output levels
/run/verbose 1
/event/verbose 0
/tracking/verbose 0

# Physics initialization
/run/initialize

# Geometry check
/geometry/test/run
"""


# ── Module file map ──────────────────────────────────────────────────

MOCK_MODULE_FILES: dict[str, list[dict[str, str]]] = {
    "simulation_core": [
        {"path": "include/MaterialRegistry.hh", "new_content": _MATERIAL_HH},
        {"path": "src/MaterialRegistry.cc", "new_content": _MATERIAL_CC},
        {"path": "include/PlacementManager.hh", "new_content": _PLACEMENT_HH},
        {"path": "src/PlacementManager.cc", "new_content": _PLACEMENT_CC},
        {"path": "include/DetectorConstruction.hh", "new_content": _GEOMETRY_HH},
        {"path": "src/DetectorConstruction.cc", "new_content": _GEOMETRY_CC},
        {"path": "include/SensitiveDetector.hh", "new_content": _SD_HH},
        {"path": "src/SensitiveDetector.cc", "new_content": _SD_CC},
        {"path": "include/ScoringManager.hh", "new_content": _SCORING_HH},
        {"path": "src/ScoringManager.cc", "new_content": _SCORING_CC},
    ],
    "beam_physics": [
        {"path": "include/PrimaryGeneratorAction.hh", "new_content": _SOURCE_HH},
        {"path": "src/PrimaryGeneratorAction.cc", "new_content": _SOURCE_CC},
        {"path": "include/PhysicsListFactoryWrapper.hh", "new_content": _PHYSICS_HH},
        {"path": "src/PhysicsListFactoryWrapper.cc", "new_content": _PHYSICS_CC},
        {"path": "macros/physics_list.mac", "new_content": _PHYSICS_MAC},
    ],
    "runtime_app": [
        {"path": "include/OutputManager.hh", "new_content": _OUTPUT_HH},
        {"path": "src/OutputManager.cc", "new_content": _OUTPUT_CC},
        {"path": "include/ActionInitialization.hh", "new_content": _ACTION_INIT_HH},
        {"path": "src/ActionInitialization.cc", "new_content": _ACTION_INIT_CC},
        {"path": "include/RunAction.hh", "new_content": _RUN_ACTION_HH},
        {"path": "src/RunAction.cc", "new_content": _RUN_ACTION_CC},
        {"path": "include/EventAction.hh", "new_content": _EVENT_ACTION_HH},
        {"path": "src/EventAction.cc", "new_content": _EVENT_ACTION_CC},
        {"path": "include/SteppingAction.hh", "new_content": _STEPPING_ACTION_HH},
        {"path": "src/SteppingAction.cc", "new_content": _STEPPING_ACTION_CC},
        {"path": "main.cc", "new_content": _MAIN_CC},
        {"path": "CMakeLists.txt", "new_content": _CMAKELISTS},
        {"path": "macros/run.mac", "new_content": _RUN_MAC},
        {"path": "macros/init.mac", "new_content": _INIT_MAC},
    ],
}


def _build_codegen_result(module_name: str) -> dict[str, Any]:
    """Build a ModuleAgentResult-style dict for CODEGEN tasks."""
    files = MOCK_MODULE_FILES.get(module_name, [])
    return {
        "status": "success",
        "module_name": module_name,
        "generated_files": [{"path": f["path"], "new_content": f["new_content"]} for f in files],
        "compilation_notes": f"Mock generated {len(files)} files for module '{module_name}'.",
        "warnings": [],
    }


def _build_gate_result(module_name: str) -> dict[str, Any]:
    """Build a GATE_EXPLANATION result — always passes in mock mode."""
    return {
        "status": "pass",
        "module_name": module_name,
        "overall_score": 1.0,
        "dimensions": {
            "contract_compliance": 1.0,
            "geant4_correctness": 1.0,
            "interface_consistency": 1.0,
            "hallucination_risk": 1.0,
            "compile_risk": 1.0,
            "cross_module_consistency": 1.0,
            "geant4_lifecycle_correctness": 1.0,
            "interface_compatibility": 1.0,
            "build_and_artifact_risk": 1.0,
        },
        "semantic_checks": [],
        "checks": [],
        "risks": [],
        "blocking_issues": [],
        "required_fixes": [],
        "requires_human_confirmation": False,
        "reviewer_notes": "mock pass",
    }


def _build_diagnosis_result(module_name: str) -> dict[str, Any]:
    """Build a FAILURE_DIAGNOSIS result — returns fixed files."""
    files = MOCK_MODULE_FILES.get(module_name, [])
    return {
        "status": "success",
        "module_name": module_name,
        "diagnosis": "Mock failure diagnosis: applied standard fix.",
        "generated_files": [{"path": f["path"], "new_content": f["new_content"]} for f in files],
        "fixes_applied": ["mock_fix_1"],
        "warnings": [],
    }


def _build_final_review_result(module_name: str) -> dict[str, Any]:
    if module_name == "physics_quality_reviewer":
        return {
            "status": "pass",
            "overall_score": 90,
            "physics_model_score": 90,
            "source_fidelity_score": 90,
            "geometry_fidelity_score": 90,
            "transport_precision_score": 85,
            "output_validity_score": 90,
            "findings": [],
            "required_fixes": [],
            "reviewer_notes": "mock physics review pass",
        }
    return {
        "status": "pass",
        "overall_score": 90,
        "findings": [],
        "required_fixes": [],
    }


def _build_simulation_briefing_result() -> dict[str, Any]:
    return {
        "status": "ready_for_approval",
        "understanding": "User wants to start a controlled Geant4 simulation workflow.",
        "questions": [],
        "recommendations": ["Run a small validation event count before production."],
        "draft_plan": {
            "objective": "Generate and validate a Geant4 simulation.",
            "simulation_scope": ["geant4"],
            "geometry": {"summary": "Use the geometry described by the user."},
            "materials": [],
            "source": {"summary": "Use the particle source described by the user."},
            "physics": {"physics_list": "FTFP_BERT"},
            "scoring": [{"quantity": "energy_deposition"}],
            "run_plan": {"validation_events": 100, "production_events": 1000},
            "codegen_constraints": ["Keep generated modules explicit and testable."],
        },
        "missing_critical_fields": [],
        "assumptions": ["Unspecified dimensions and materials must be confirmed downstream."],
        "risks": ["The generated model may require human confirmation for missing details."],
        "final_query": "Build a controlled Geant4 simulation from the user's approved brief.",
        "proposed_command": {
            "name": "start_job",
            "args": {
                "query": "Build a controlled Geant4 simulation from the user's approved brief.",
                "run_mode": "strict",
            },
            "risk": "write",
            "status": "pending",
            "summary": "Start the approved controlled Geant4 simulation workflow.",
        },
        "approval_request": {
            "requires_human_approval": True,
            "summary": "Start the controlled Geant4 simulation workflow.",
            "risks": ["Missing details may trigger human confirmation."],
        },
    }


def call_mock_model(
    task: ModelTask,
    metadata: dict[str, Any],
) -> ModelCallResult:
    """Return a deterministic ModelCallResult based on task type."""

    module_name = metadata.get("module_name", "unknown")

    if task == ModelTask.CODEGEN:
        parsed = _build_codegen_result(module_name)
    elif task == ModelTask.GATE_EXPLANATION:
        parsed = _build_gate_result(module_name)
    elif task == ModelTask.FAILURE_DIAGNOSIS:
        parsed = _build_diagnosis_result(module_name)
    elif task == ModelTask.FINAL_REVIEW:
        parsed = _build_final_review_result(module_name)
    elif task == ModelTask.SIMULATION_BRIEFING:
        parsed = _build_simulation_briefing_result()
    else:
        parsed = {
            "status": "success",
            "task": str(task),
            "message": f"Mock response for task '{task}'.",
        }

    content = json.dumps(parsed)

    return ModelCallResult(
        task=task,
        tier=metadata.get("tier", "lite"),
        provider=ModelProvider.MOCK,
        model_name="mock",
        content=content,
        parsed_json=parsed,
        usage={"mock": True},
        latency_ms=0.0,
    )
