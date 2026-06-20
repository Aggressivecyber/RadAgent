"""Canonical minimal Geant4 project scaffold for RadAgent codegen jobs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_core.g4_codegen.cmake_template import RADAGENT_CMAKE_TEMPLATE

TEMPLATE_VERSION = "radagent_g4_minimal_v1"

OUTPUT_CONTRACT = [
    "g4_summary.json",
    "event_table.csv",
    "edep_3d.csv",
    "dose_3d.csv",
    "geometry_view.json",
    "particle_tracks.json",
    "energy_deposits.json",
    "provenance.json",
]


def create_minimal_geant4_project(
    project_dir: str | Path,
    *,
    events: int = 100,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create the canonical minimal, extensible Geant4 project scaffold."""
    root = Path(project_dir)
    root.mkdir(parents=True, exist_ok=True)
    files = _template_files(max(1, int(events)))
    written: list[str] = []
    preserved: list[str] = []
    for relative, content in files.items():
        target = root / relative
        if target.exists() and not overwrite:
            preserved.append(relative)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(relative)
    return {
        "template_version": TEMPLATE_VERSION,
        "files": sorted(files),
        "written_files": sorted(written),
        "preserved_files": sorted(preserved),
        "events": max(1, int(events)),
        "output_contract": list(OUTPUT_CONTRACT),
    }


def _template_files(events: int) -> dict[str, str]:
    config = {
        "template_version": TEMPLATE_VERSION,
        "run": {"events": events, "macro": "macros/run.mac"},
        "source": {
            "particle": "gamma",
            "energy_MeV": 1.0,
            "position_mm": [0.0, 0.0, -400.0],
            "direction": [0.0, 0.0, 1.0],
        },
        "geometry": {
            "world": {"material": "G4_AIR", "size_mm": [1000.0, 1000.0, 1000.0]},
            "detector": {"material": "G4_Si", "size_mm": [100.0, 100.0, 10.0]},
        },
        "physics": {
            "physics_list": "FTFP_BERT",
            "production_cuts_mm": {
                "gamma": 0.1,
                "electron": 0.1,
                "positron": 0.1,
                "proton": 0.1,
            },
            "rationale": (
                "Template defaults are conservative starter values. Codegen agents may "
                "replace them with task-specific cuts after reading the model IR."
            ),
        },
        "limits": {
            "detector_max_step_mm": 0.1,
            "world_max_step_mm": 10.0,
            "max_track_length_mm": 2000.0,
            "max_track_time_ns": 1000.0,
            "min_kinetic_energy_MeV": 0.001,
        },
        "output_contract": OUTPUT_CONTRACT,
        "extension_points": [
            "MaterialRegistry",
            "DetectorConstruction",
            "PrimaryGeneratorAction",
            "ScoringManager",
            "OutputManager",
        ],
    }
    return {
        "CMakeLists.txt": RADAGENT_CMAKE_TEMPLATE,
        "main.cc": MAIN_CC,
        "config/simulation_config.json": json.dumps(config, indent=2, ensure_ascii=False)
        + "\n",
        "include/ActionInitialization.hh": ACTION_INITIALIZATION_HH,
        "include/DetectorConstruction.hh": DETECTOR_CONSTRUCTION_HH,
        "include/EventAction.hh": EVENT_ACTION_HH,
        "include/Hit.hh": HIT_HH,
        "include/MaterialRegistry.hh": MATERIAL_REGISTRY_HH,
        "include/OutputManager.hh": OUTPUT_MANAGER_HH,
        "include/PrimaryGeneratorAction.hh": PRIMARY_GENERATOR_ACTION_HH,
        "include/RunAction.hh": RUN_ACTION_HH,
        "include/ScoringManager.hh": SCORING_MANAGER_HH,
        "include/SensitiveDetector.hh": SENSITIVE_DETECTOR_HH,
        "include/SteppingAction.hh": STEPPING_ACTION_HH,
        "src/ActionInitialization.cc": ACTION_INITIALIZATION_CC,
        "src/DetectorConstruction.cc": DETECTOR_CONSTRUCTION_CC,
        "src/EventAction.cc": EVENT_ACTION_CC,
        "src/Hit.cc": HIT_CC,
        "src/MaterialRegistry.cc": MATERIAL_REGISTRY_CC,
        "src/OutputManager.cc": OUTPUT_MANAGER_CC,
        "src/PrimaryGeneratorAction.cc": PRIMARY_GENERATOR_ACTION_CC,
        "src/RunAction.cc": RUN_ACTION_CC,
        "src/ScoringManager.cc": SCORING_MANAGER_CC,
        "src/SensitiveDetector.cc": SENSITIVE_DETECTOR_CC,
        "src/SteppingAction.cc": STEPPING_ACTION_CC,
        "macros/run.mac": f"/run/initialize\n/run/beamOn {events}\n",
        "macros/radagent_self_check_100.mac": "/run/initialize\n/run/beamOn 100\n",
    }


MAIN_CC = r"""#include "ActionInitialization.hh"
#include "DetectorConstruction.hh"
#include "OutputManager.hh"

#include "FTFP_BERT.hh"
#include "G4ProductionCuts.hh"
#include "G4RunManagerFactory.hh"
#include "G4SystemOfUnits.hh"
#include "G4UIExecutive.hh"
#include "G4UImanager.hh"
#include "G4VisExecutive.hh"

#include <memory>

int main(int argc, char** argv)
{
  auto* runManager = G4RunManagerFactory::CreateRunManager(G4RunManagerType::Serial);
  auto outputManager = std::make_unique<OutputManager>("output");
  auto* physicsList = new FTFP_BERT;
  physicsList->SetDefaultCutValue(0.1 * mm);

  runManager->SetUserInitialization(new DetectorConstruction(outputManager.get()));
  runManager->SetUserInitialization(physicsList);
  runManager->SetUserInitialization(new ActionInitialization(outputManager.get()));

  auto visManager = std::make_unique<G4VisExecutive>();
  visManager->Initialize();

  auto* ui = G4UImanager::GetUIpointer();
  if (argc > 1) {
    ui->ApplyCommand(G4String("/control/execute ") + argv[1]);
  } else {
    ui->ApplyCommand("/control/execute macros/run.mac");
  }

  delete runManager;
  return 0;
}
"""


ACTION_INITIALIZATION_HH = r"""#ifndef RADAGENT_ACTION_INITIALIZATION_HH
#define RADAGENT_ACTION_INITIALIZATION_HH

#include "G4VUserActionInitialization.hh"

class OutputManager;

class ActionInitialization : public G4VUserActionInitialization
{
public:
  explicit ActionInitialization(OutputManager* outputManager);
  ~ActionInitialization() override = default;

  void Build() const override;

private:
  OutputManager* fOutputManager;
};

#endif
"""


ACTION_INITIALIZATION_CC = r"""#include "ActionInitialization.hh"

#include "EventAction.hh"
#include "OutputManager.hh"
#include "PrimaryGeneratorAction.hh"
#include "RunAction.hh"
#include "SteppingAction.hh"

ActionInitialization::ActionInitialization(OutputManager* outputManager)
  : fOutputManager(outputManager)
{
}

void ActionInitialization::Build() const
{
  SetUserAction(new PrimaryGeneratorAction());
  SetUserAction(new RunAction(fOutputManager));
  SetUserAction(new EventAction(fOutputManager));
  SetUserAction(new SteppingAction(fOutputManager));
}
"""


DETECTOR_CONSTRUCTION_HH = r"""#ifndef RADAGENT_DETECTOR_CONSTRUCTION_HH
#define RADAGENT_DETECTOR_CONSTRUCTION_HH

#include "G4VUserDetectorConstruction.hh"

class G4LogicalVolume;
class G4VPhysicalVolume;
class OutputManager;

class DetectorConstruction : public G4VUserDetectorConstruction
{
public:
  explicit DetectorConstruction(OutputManager* outputManager);
  ~DetectorConstruction() override = default;

  G4VPhysicalVolume* Construct() override;
  void ConstructSDandField() override;

  G4LogicalVolume* GetDetectorLogicalVolume() const { return fDetectorLogical; }

private:
  OutputManager* fOutputManager;
  G4LogicalVolume* fDetectorLogical = nullptr;
};

#endif
"""


DETECTOR_CONSTRUCTION_CC = r"""#include "DetectorConstruction.hh"

#include "MaterialRegistry.hh"
#include "OutputManager.hh"
#include "SensitiveDetector.hh"

#include "G4Box.hh"
#include "G4Colour.hh"
#include "G4LogicalVolume.hh"
#include "G4NistManager.hh"
#include "G4PVPlacement.hh"
#include "G4SDManager.hh"
#include "G4SystemOfUnits.hh"
#include "G4UserLimits.hh"
#include "G4VisAttributes.hh"

DetectorConstruction::DetectorConstruction(OutputManager* outputManager)
  : fOutputManager(outputManager)
{
}

G4VPhysicalVolume* DetectorConstruction::Construct()
{
  MaterialRegistry materials;
  auto* air = materials.Get("G4_AIR");
  auto* silicon = materials.Get("G4_Si");

  auto* worldSolid = new G4Box("world_solid", 500.0 * mm, 500.0 * mm, 500.0 * mm);
  auto* worldLogical = new G4LogicalVolume(worldSolid, air, "world_logical");
  worldLogical->SetUserLimits(new G4UserLimits(
    10.0 * mm,
    2000.0 * mm,
    1000.0 * ns,
    0.001 * MeV));
  auto* worldPhysical = new G4PVPlacement(
    nullptr, {}, worldLogical, "world", nullptr, false, 0, true);

  auto* detectorSolid = new G4Box("detector_solid", 50.0 * mm, 50.0 * mm, 5.0 * mm);
  fDetectorLogical = new G4LogicalVolume(detectorSolid, silicon, "detector_logical");
  fDetectorLogical->SetUserLimits(new G4UserLimits(
    0.1 * mm,
    2000.0 * mm,
    1000.0 * ns,
    0.001 * MeV));
  new G4PVPlacement(
    nullptr, {}, fDetectorLogical, "silicon_detector", worldLogical, false, 0, true);

  auto* worldVis = new G4VisAttributes(G4Colour(0.8, 0.9, 1.0, 0.08));
  worldVis->SetVisibility(true);
  worldLogical->SetVisAttributes(worldVis);

  auto* detectorVis = new G4VisAttributes(G4Colour(0.1, 0.45, 0.9, 0.45));
  detectorVis->SetVisibility(true);
  detectorVis->SetForceSolid(true);
  fDetectorLogical->SetVisAttributes(detectorVis);

  if (fOutputManager) {
    fOutputManager->SetGeometryDescription("world", "G4_AIR", {1000.0, 1000.0, 1000.0}, "box");
    fOutputManager->SetGeometryDescription("silicon_detector", "G4_Si", {100.0, 100.0, 10.0}, "box");
  }
  return worldPhysical;
}

void DetectorConstruction::ConstructSDandField()
{
  if (!fDetectorLogical) {
    return;
  }
  auto* sd = new SensitiveDetector("RadAgentSensitiveDetector", fOutputManager);
  G4SDManager::GetSDMpointer()->AddNewDetector(sd);
  fDetectorLogical->SetSensitiveDetector(sd);
}
"""


MATERIAL_REGISTRY_HH = r"""#ifndef RADAGENT_MATERIAL_REGISTRY_HH
#define RADAGENT_MATERIAL_REGISTRY_HH

#include "G4String.hh"

class G4Material;

class MaterialRegistry
{
public:
  MaterialRegistry() = default;
  G4Material* Get(const G4String& materialName) const;
};

#endif
"""


MATERIAL_REGISTRY_CC = r"""#include "MaterialRegistry.hh"

#include "G4Material.hh"
#include "G4NistManager.hh"

G4Material* MaterialRegistry::Get(const G4String& materialName) const
{
  return G4NistManager::Instance()->FindOrBuildMaterial(materialName);
}
"""


PRIMARY_GENERATOR_ACTION_HH = r"""#ifndef RADAGENT_PRIMARY_GENERATOR_ACTION_HH
#define RADAGENT_PRIMARY_GENERATOR_ACTION_HH

#include "G4VUserPrimaryGeneratorAction.hh"

class G4Event;
class G4ParticleGun;

class PrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction
{
public:
  PrimaryGeneratorAction();
  ~PrimaryGeneratorAction() override;

  void GeneratePrimaries(G4Event* event) override;

private:
  G4ParticleGun* fParticleGun;
};

#endif
"""


PRIMARY_GENERATOR_ACTION_CC = r"""#include "PrimaryGeneratorAction.hh"

#include "G4Event.hh"
#include "G4Gamma.hh"
#include "G4ParticleGun.hh"
#include "G4SystemOfUnits.hh"
#include "G4ThreeVector.hh"

PrimaryGeneratorAction::PrimaryGeneratorAction()
{
  fParticleGun = new G4ParticleGun(1);
  fParticleGun->SetParticleDefinition(G4Gamma::GammaDefinition());
  fParticleGun->SetParticleEnergy(1.0 * MeV);
  fParticleGun->SetParticlePosition(G4ThreeVector(0.0, 0.0, -400.0 * mm));
  fParticleGun->SetParticleMomentumDirection(G4ThreeVector(0.0, 0.0, 1.0));
}

PrimaryGeneratorAction::~PrimaryGeneratorAction()
{
  delete fParticleGun;
}

void PrimaryGeneratorAction::GeneratePrimaries(G4Event* event)
{
  fParticleGun->GeneratePrimaryVertex(event);
}
"""


OUTPUT_MANAGER_HH = r"""#ifndef RADAGENT_OUTPUT_MANAGER_HH
#define RADAGENT_OUTPUT_MANAGER_HH

#include "G4String.hh"
#include "G4ThreeVector.hh"

#include <array>
#include <map>
#include <string>
#include <vector>

class G4Run;

struct TrackPoint
{
  int eventId = 0;
  int trackId = 0;
  std::string particle;
  double x_mm = 0.0;
  double y_mm = 0.0;
  double z_mm = 0.0;
  double kinetic_MeV = 0.0;
};

struct EnergyDeposit
{
  int eventId = 0;
  int trackId = 0;
  std::string volume;
  double x_mm = 0.0;
  double y_mm = 0.0;
  double z_mm = 0.0;
  double edep_MeV = 0.0;
};

struct EventSummary
{
  int eventId = 0;
  double edep_MeV = 0.0;
};

struct GeometryDescription
{
  std::string material;
  std::string shape = "box";
  std::array<double, 3> sizeMm = {1.0, 1.0, 1.0};
};

class OutputManager
{
public:
  explicit OutputManager(G4String outputDirectory);

  void BeginEvent(int eventId);
  void RecordTrackPoint(
    int eventId,
    int trackId,
    const std::string& particle,
    const G4ThreeVector& position,
    double kineticEnergy);
  void RecordEnergyDeposit(
    int eventId,
    int trackId,
    const std::string& volume,
    const G4ThreeVector& position,
    double energyDeposit);
  void EndEvent(int eventId);
  void SetGeometryDescription(
    const std::string& componentId,
    const std::string& material,
    const std::array<double, 3>& sizeMm,
    const std::string& shape = "box");
  void WriteAll(const G4Run* run = nullptr) const;

private:
  G4String fOutputDirectory;
  int fCurrentEventId = -1;
  double fCurrentEventEdep = 0.0;
  std::vector<TrackPoint> fTrackPoints;
  std::vector<EnergyDeposit> fDeposits;
  std::vector<EventSummary> fEvents;
  std::map<std::string, GeometryDescription> fGeometry;
};

#endif
"""


OUTPUT_MANAGER_CC = r"""#include "OutputManager.hh"

#include "G4Run.hh"
#include "G4SystemOfUnits.hh"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>

namespace
{
G4String resolveOutputDirectory(const G4String& fallback)
{
  const char* outputEnv = std::getenv("G4_OUTPUT_DIR");
  if (outputEnv && outputEnv[0] != '\0') {
    return G4String(outputEnv);
  }
  return fallback;
}

std::string pathJoin(const G4String& root, const std::string& fileName)
{
  return std::string(root) + "/" + fileName;
}
}

OutputManager::OutputManager(G4String outputDirectory)
  : fOutputDirectory(resolveOutputDirectory(outputDirectory))
{
}

void OutputManager::BeginEvent(int eventId)
{
  fCurrentEventId = eventId;
  fCurrentEventEdep = 0.0;
}

void OutputManager::RecordTrackPoint(
  int eventId,
  int trackId,
  const std::string& particle,
  const G4ThreeVector& position,
  double kineticEnergy)
{
  fTrackPoints.push_back({
    eventId,
    trackId,
    particle,
    position.x() / mm,
    position.y() / mm,
    position.z() / mm,
    kineticEnergy / MeV,
  });
}

void OutputManager::RecordEnergyDeposit(
  int eventId,
  int trackId,
  const std::string& volume,
  const G4ThreeVector& position,
  double energyDeposit)
{
  if (energyDeposit <= 0.0) {
    return;
  }
  fCurrentEventEdep += energyDeposit / MeV;
  fDeposits.push_back({
    eventId,
    trackId,
    volume,
    position.x() / mm,
    position.y() / mm,
    position.z() / mm,
    energyDeposit / MeV,
  });
}

void OutputManager::EndEvent(int eventId)
{
  fEvents.push_back({eventId, fCurrentEventEdep});
}

void OutputManager::SetGeometryDescription(
  const std::string& componentId,
  const std::string& material,
  const std::array<double, 3>& sizeMm,
  const std::string& shape)
{
  fGeometry[componentId] = {material, shape, sizeMm};
}

void OutputManager::WriteAll(const G4Run* run) const
{
  std::filesystem::create_directories(std::string(fOutputDirectory));

  double totalEdep = 0.0;
  for (const auto& row : fEvents) {
    totalEdep += row.edep_MeV;
  }

  {
    std::ofstream out(pathJoin(fOutputDirectory, "g4_summary.json"));
    out << "{\n";
    out << "  \"schema_version\": \"radagent_g4_summary_v1\",\n";
    out << "  \"template_version\": \"radagent_g4_minimal_v1\",\n";
    out << "  \"events_requested\": " << (run ? run->GetNumberOfEventToBeProcessed() : 0) << ",\n";
    out << "  \"events_recorded\": " << fEvents.size() << ",\n";
    out << "  \"total_edep_MeV\": " << std::setprecision(12) << totalEdep << "\n";
    out << "}\n";
  }

  {
    std::ofstream out(pathJoin(fOutputDirectory, "event_table.csv"));
    out << "event_id,total_edep_MeV\n";
    for (const auto& row : fEvents) {
      out << row.eventId << "," << std::setprecision(12) << row.edep_MeV << "\n";
    }
  }

  {
    std::ofstream out(pathJoin(fOutputDirectory, "edep_3d.csv"));
    out << "event_id,track_id,volume,x_mm,y_mm,z_mm,edep_MeV\n";
    for (const auto& row : fDeposits) {
      out << row.eventId << "," << row.trackId << "," << row.volume << ","
          << row.x_mm << "," << row.y_mm << "," << row.z_mm << ","
          << std::setprecision(12) << row.edep_MeV << "\n";
    }
  }

  {
    std::ofstream out(pathJoin(fOutputDirectory, "dose_3d.csv"));
    out << "voxel_id,x_mm,y_mm,z_mm,dose_Gy\n";
    int index = 0;
    for (const auto& row : fDeposits) {
      out << index++ << "," << row.x_mm << "," << row.y_mm << "," << row.z_mm
          << "," << std::setprecision(12) << row.edep_MeV << "\n";
    }
  }

  {
    std::ofstream out(pathJoin(fOutputDirectory, "geometry_view.json"));
    out << "{\n  \"components\": [\n";
    bool first = true;
    for (const auto& item : fGeometry) {
      if (!first) {
        out << ",\n";
      }
      first = false;
      const auto& geometry = item.second;
      const auto& size = geometry.sizeMm;
      out << "    {\"id\": \"" << item.first << "\", \"material\": \""
          << geometry.material << "\", \"shape\": \"" << geometry.shape
          << "\", \"size_mm\": ["
          << size[0] << ", " << size[1] << ", " << size[2] << "]}";
    }
    out << "\n  ]\n}\n";
  }

  {
    std::ofstream out(pathJoin(fOutputDirectory, "particle_tracks.json"));
    out << "{\n  \"tracks\": [\n";
    for (std::size_t i = 0; i < fTrackPoints.size(); ++i) {
      const auto& row = fTrackPoints[i];
      if (i != 0) {
        out << ",\n";
      }
      out << "    {\"event_id\": " << row.eventId << ", \"track_id\": " << row.trackId
          << ", \"particle\": \"" << row.particle << "\", \"position_mm\": ["
          << row.x_mm << ", " << row.y_mm << ", " << row.z_mm
          << "], \"kinetic_MeV\": " << row.kinetic_MeV << "}";
    }
    out << "\n  ]\n}\n";
  }

  {
    std::ofstream out(pathJoin(fOutputDirectory, "energy_deposits.json"));
    out << "{\n  \"deposits\": [\n";
    for (std::size_t i = 0; i < fDeposits.size(); ++i) {
      const auto& row = fDeposits[i];
      if (i != 0) {
        out << ",\n";
      }
      out << "    {\"event_id\": " << row.eventId << ", \"track_id\": " << row.trackId
          << ", \"volume\": \"" << row.volume << "\", \"position_mm\": ["
          << row.x_mm << ", " << row.y_mm << ", " << row.z_mm
          << "], \"edep_MeV\": " << row.edep_MeV << "}";
    }
    out << "\n  ]\n}\n";
  }

  {
    std::ofstream out(pathJoin(fOutputDirectory, "provenance.json"));
    out << "{\n";
    out << "  \"generator\": \"RadAgent minimal Geant4 template\",\n";
    out << "  \"template_version\": \"radagent_g4_minimal_v1\",\n";
    out << "  \"output_contract\": [\"g4_summary.json\", \"event_table.csv\", \"edep_3d.csv\", \"dose_3d.csv\", \"geometry_view.json\", \"particle_tracks.json\", \"energy_deposits.json\", \"provenance.json\"]\n";
    out << "}\n";
  }
}
"""


EVENT_ACTION_HH = r"""#ifndef RADAGENT_EVENT_ACTION_HH
#define RADAGENT_EVENT_ACTION_HH

#include "G4UserEventAction.hh"

class G4Event;
class OutputManager;

class EventAction : public G4UserEventAction
{
public:
  explicit EventAction(OutputManager* outputManager);
  ~EventAction() override = default;

  void BeginOfEventAction(const G4Event* event) override;
  void EndOfEventAction(const G4Event* event) override;

private:
  OutputManager* fOutputManager;
};

#endif
"""


EVENT_ACTION_CC = r"""#include "EventAction.hh"

#include "OutputManager.hh"

#include "G4Event.hh"

EventAction::EventAction(OutputManager* outputManager)
  : fOutputManager(outputManager)
{
}

void EventAction::BeginOfEventAction(const G4Event* event)
{
  if (fOutputManager) {
    fOutputManager->BeginEvent(event->GetEventID());
  }
}

void EventAction::EndOfEventAction(const G4Event* event)
{
  if (fOutputManager) {
    fOutputManager->EndEvent(event->GetEventID());
  }
}
"""


RUN_ACTION_HH = r"""#ifndef RADAGENT_RUN_ACTION_HH
#define RADAGENT_RUN_ACTION_HH

#include "G4UserRunAction.hh"

class G4Run;
class OutputManager;

class RunAction : public G4UserRunAction
{
public:
  explicit RunAction(OutputManager* outputManager);
  ~RunAction() override = default;

  void EndOfRunAction(const G4Run* run) override;

private:
  OutputManager* fOutputManager;
};

#endif
"""


RUN_ACTION_CC = r"""#include "RunAction.hh"

#include "OutputManager.hh"

RunAction::RunAction(OutputManager* outputManager)
  : fOutputManager(outputManager)
{
}

void RunAction::EndOfRunAction(const G4Run* run)
{
  if (fOutputManager) {
    fOutputManager->WriteAll(run);
  }
}
"""


STEPPING_ACTION_HH = r"""#ifndef RADAGENT_STEPPING_ACTION_HH
#define RADAGENT_STEPPING_ACTION_HH

#include "G4UserSteppingAction.hh"

class G4Step;
class OutputManager;

class SteppingAction : public G4UserSteppingAction
{
public:
  explicit SteppingAction(OutputManager* outputManager);
  ~SteppingAction() override = default;

  void UserSteppingAction(const G4Step* step) override;

private:
  OutputManager* fOutputManager;
};

#endif
"""


STEPPING_ACTION_CC = r"""#include "SteppingAction.hh"

#include "OutputManager.hh"

#include "G4Event.hh"
#include "G4EventManager.hh"
#include "G4Step.hh"
#include "G4SystemOfUnits.hh"
#include "G4Track.hh"
#include "G4VPhysicalVolume.hh"

SteppingAction::SteppingAction(OutputManager* outputManager)
  : fOutputManager(outputManager)
{
}

void SteppingAction::UserSteppingAction(const G4Step* step)
{
  if (!fOutputManager || !step) {
    return;
  }
  const auto* event = G4EventManager::GetEventManager()->GetConstCurrentEvent();
  if (!event) {
    return;
  }
  const auto* track = step->GetTrack();
  const auto* prePoint = step->GetPreStepPoint();
  const auto* volume = prePoint->GetPhysicalVolume();
  const std::string volumeName = volume ? volume->GetName() : "unknown";

  fOutputManager->RecordTrackPoint(
    event->GetEventID(),
    track->GetTrackID(),
    track->GetDefinition()->GetParticleName(),
    prePoint->GetPosition(),
    track->GetKineticEnergy());
  fOutputManager->RecordEnergyDeposit(
    event->GetEventID(),
    track->GetTrackID(),
    volumeName,
    prePoint->GetPosition(),
    step->GetTotalEnergyDeposit());
}
"""


SENSITIVE_DETECTOR_HH = r"""#ifndef RADAGENT_SENSITIVE_DETECTOR_HH
#define RADAGENT_SENSITIVE_DETECTOR_HH

#include "G4VSensitiveDetector.hh"

class G4HCofThisEvent;
class G4Step;
class OutputManager;

class SensitiveDetector : public G4VSensitiveDetector
{
public:
  SensitiveDetector(const G4String& name, OutputManager* outputManager);
  ~SensitiveDetector() override = default;

  G4bool ProcessHits(G4Step* step, G4TouchableHistory* history) override;

private:
  OutputManager* fOutputManager;
};

#endif
"""


SENSITIVE_DETECTOR_CC = r"""#include "SensitiveDetector.hh"

#include "OutputManager.hh"

#include "G4Event.hh"
#include "G4EventManager.hh"
#include "G4Step.hh"
#include "G4Track.hh"
#include "G4VPhysicalVolume.hh"

SensitiveDetector::SensitiveDetector(const G4String& name, OutputManager* outputManager)
  : G4VSensitiveDetector(name),
    fOutputManager(outputManager)
{
}

G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory*)
{
  // SteppingAction is the single source of truth for deposits and tracks.
  (void)fOutputManager;
  (void)step;
  return true;
}
"""


SCORING_MANAGER_HH = r"""#ifndef RADAGENT_SCORING_MANAGER_HH
#define RADAGENT_SCORING_MANAGER_HH

#include <string>
#include <vector>

class ScoringManager
{
public:
  void AddSensitiveVolume(const std::string& volumeName);
  const std::vector<std::string>& SensitiveVolumes() const;

private:
  std::vector<std::string> fSensitiveVolumes;
};

#endif
"""


SCORING_MANAGER_CC = r"""#include "ScoringManager.hh"

void ScoringManager::AddSensitiveVolume(const std::string& volumeName)
{
  fSensitiveVolumes.push_back(volumeName);
}

const std::vector<std::string>& ScoringManager::SensitiveVolumes() const
{
  return fSensitiveVolumes;
}
"""


HIT_HH = r"""#ifndef RADAGENT_HIT_HH
#define RADAGENT_HIT_HH

#include "G4VHit.hh"
#include "G4ThreeVector.hh"

class Hit : public G4VHit
{
public:
  Hit() = default;
  ~Hit() override = default;

  int eventId = 0;
  int trackId = 0;
  G4ThreeVector position;
  double edep = 0.0;
};

#endif
"""


HIT_CC = r"""#include "Hit.hh"
"""
