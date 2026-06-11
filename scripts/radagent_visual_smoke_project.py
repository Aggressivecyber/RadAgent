"""Generate a small RadAgent-owned Geant4 visual smoke project.

The fixture is intentionally independent of Geant4 examples: it exercises the
visual workbench contract with an external incident source and explicit
visualization attributes.
"""

from __future__ import annotations

from pathlib import Path


def create_radagent_visual_smoke_project(project_dir: str | Path) -> Path:
    """Write a minimal external-beam Geant4 project and return its root."""
    root = Path(project_dir)
    (root / "include").mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "macros").mkdir(parents=True, exist_ok=True)

    _write(root / "CMakeLists.txt", _cmake())
    _write(root / "main.cc", _main_cc())
    _write(root / "include" / "DetectorConstruction.hh", _detector_hh())
    _write(root / "src" / "DetectorConstruction.cc", _detector_cc())
    _write(root / "include" / "PrimaryGeneratorAction.hh", _primary_hh())
    _write(root / "src" / "PrimaryGeneratorAction.cc", _primary_cc())
    _write(root / "include" / "ActionInitialization.hh", _action_hh())
    _write(root / "src" / "ActionInitialization.cc", _action_cc())
    _write(root / "macros" / "run.mac", _run_macro())
    _write(root / "macros" / "init_vis.mac", _init_vis_macro())
    _write(root / "macros" / "init.mac", _init_vis_macro())
    _write(root / "macros" / "vis.mac", _vis_macro())
    _write(root / "macros" / "gui.mac", _gui_macro())
    return root


def _write(path: Path, text: str) -> None:
    path.write_text(text.strip() + "\n", encoding="utf-8")


def _cmake() -> str:
    return """
cmake_minimum_required(VERSION 3.16)
project(radagent_visual_smoke)

find_package(Geant4 REQUIRED ui_all vis_all)
include(${Geant4_USE_FILE})

add_executable(radagent_visual_smoke
  main.cc
  src/ActionInitialization.cc
  src/DetectorConstruction.cc
  src/PrimaryGeneratorAction.cc
)
target_include_directories(radagent_visual_smoke PRIVATE include)
target_link_libraries(radagent_visual_smoke ${Geant4_LIBRARIES})

file(COPY macros DESTINATION ${CMAKE_BINARY_DIR})
"""


def _main_cc() -> str:
    return r"""
#include "ActionInitialization.hh"
#include "DetectorConstruction.hh"

#include "FTFP_BERT.hh"
#include "G4RunManagerFactory.hh"
#include "G4UIExecutive.hh"
#include "G4UImanager.hh"
#include "G4VisExecutive.hh"

int main(int argc, char** argv)
{
  G4UIExecutive* ui = nullptr;
  if (argc == 1) {
    ui = new G4UIExecutive(argc, argv);
  }

  auto runManager = G4RunManagerFactory::CreateRunManager(G4RunManagerType::Default);
  runManager->SetUserInitialization(new DetectorConstruction());
  runManager->SetUserInitialization(new FTFP_BERT());
  runManager->SetUserInitialization(new ActionInitialization());

  auto visManager = new G4VisExecutive(argc, argv);
  visManager->Initialize();

  auto uiManager = G4UImanager::GetUIpointer();
  if (ui == nullptr) {
    uiManager->ApplyCommand(G4String("/control/execute ") + argv[1]);
  } else {
    uiManager->ApplyCommand("/control/execute macros/init_vis.mac");
    if (ui->IsGUI()) {
      uiManager->ApplyCommand("/control/execute macros/gui.mac");
    }
    ui->SessionStart();
    delete ui;
  }

  delete visManager;
  delete runManager;
  return 0;
}
"""


def _detector_hh() -> str:
    return r"""
#pragma once

#include "G4VUserDetectorConstruction.hh"

class G4VPhysicalVolume;

class DetectorConstruction final : public G4VUserDetectorConstruction {
 public:
  DetectorConstruction() = default;
  ~DetectorConstruction() override = default;

  G4VPhysicalVolume* Construct() override;
};
"""


def _detector_cc() -> str:
    return r"""
#include "DetectorConstruction.hh"

#include "G4Box.hh"
#include "G4Colour.hh"
#include "G4LogicalVolume.hh"
#include "G4NistManager.hh"
#include "G4PVPlacement.hh"
#include "G4SystemOfUnits.hh"
#include "G4VisAttributes.hh"

G4VPhysicalVolume* DetectorConstruction::Construct()
{
  auto* nist = G4NistManager::Instance();
  auto* air = nist->FindOrBuildMaterial("G4_AIR");
  auto* silicon = nist->FindOrBuildMaterial("G4_Si");
  auto* aluminum = nist->FindOrBuildMaterial("G4_Al");
  auto* oxide = nist->FindOrBuildMaterial("G4_SILICON_DIOXIDE");

  auto* worldSolid = new G4Box("World", 50.0 * mm, 35.0 * mm, 60.0 * mm);
  auto* worldLogic = new G4LogicalVolume(worldSolid, air, "World");
  auto* worldVis = new G4VisAttributes();
  worldVis->SetVisibility(false);
  worldLogic->SetVisAttributes(worldVis);
  auto* world = new G4PVPlacement(
      nullptr, {}, worldLogic, "World", nullptr, false, 0, true);

  auto* envelopeSolid = new G4Box("AssemblyEnvelope", 24.0 * mm, 18.0 * mm, 8.0 * mm);
  auto* envelopeLogic = new G4LogicalVolume(envelopeSolid, air, "AssemblyEnvelope");
  auto* envelopeVis = new G4VisAttributes(G4Colour(0.2, 0.45, 0.85, 0.12));
  envelopeVis->SetVisibility(true);
  envelopeVis->SetForceWireframe(true);
  envelopeLogic->SetVisAttributes(envelopeVis);
  new G4PVPlacement(
      nullptr, {}, envelopeLogic, "AssemblyEnvelope", worldLogic, false, 0, true);

  // Thin entrance window, not a stopping shield: the smoke test must show
  // externally incident particles entering the device stack.
  auto* windowSolid = new G4Box("EntranceWindow", 20.0 * mm, 14.0 * mm, 0.05 * mm);
  auto* windowLogic = new G4LogicalVolume(windowSolid, aluminum, "EntranceWindow");
  auto* windowVis = new G4VisAttributes(G4Colour(0.55, 0.60, 0.68, 0.35));
  windowVis->SetVisibility(true);
  windowVis->SetForceSolid(true);
  windowLogic->SetVisAttributes(windowVis);
  new G4PVPlacement(
      nullptr, G4ThreeVector(0.0, 0.0, -7.5 * mm), windowLogic,
      "EntranceWindow", envelopeLogic, false, 0, true);

  auto* oxideSolid = new G4Box("OxideLayer", 18.0 * mm, 12.0 * mm, 0.35 * mm);
  auto* oxideLogic = new G4LogicalVolume(oxideSolid, oxide, "OxideLayer");
  auto* oxideVis = new G4VisAttributes(G4Colour(0.0, 0.75, 0.80, 0.70));
  oxideVis->SetVisibility(true);
  oxideVis->SetForceSolid(true);
  oxideLogic->SetVisAttributes(oxideVis);
  new G4PVPlacement(
      nullptr, G4ThreeVector(0.0, 0.0, -1.0 * mm), oxideLogic,
      "OxideLayer", envelopeLogic, false, 0, true);

  auto* deviceSolid = new G4Box("Device", 16.0 * mm, 10.0 * mm, 2.0 * mm);
  auto* deviceLogic = new G4LogicalVolume(deviceSolid, silicon, "Device");
  auto* deviceVis = new G4VisAttributes(G4Colour(0.95, 0.25, 0.18, 0.85));
  deviceVis->SetVisibility(true);
  deviceVis->SetForceSolid(true);
  deviceLogic->SetVisAttributes(deviceVis);
  new G4PVPlacement(
      nullptr, G4ThreeVector(0.0, 0.0, 2.0 * mm), deviceLogic,
      "Device", envelopeLogic, false, 0, true);

  return world;
}
"""


def _primary_hh() -> str:
    return r"""
#pragma once

#include "G4VUserPrimaryGeneratorAction.hh"

class G4Event;
class G4ParticleGun;

class PrimaryGeneratorAction final : public G4VUserPrimaryGeneratorAction {
 public:
  PrimaryGeneratorAction();
  ~PrimaryGeneratorAction() override;

  void GeneratePrimaries(G4Event* event) override;

 private:
  G4ParticleGun* particleGun_;
};
"""


def _primary_cc() -> str:
    return r"""
#include "PrimaryGeneratorAction.hh"

#include "G4Event.hh"
#include "G4ParticleGun.hh"
#include "G4ParticleTable.hh"
#include "G4SystemOfUnits.hh"

namespace {
constexpr G4double kSourceZ = -40.0 * mm;
}

PrimaryGeneratorAction::PrimaryGeneratorAction()
{
  particleGun_ = new G4ParticleGun(1);
  auto* particle = G4ParticleTable::GetParticleTable()->FindParticle("proton");
  particleGun_->SetParticleDefinition(particle);
  particleGun_->SetParticleEnergy(150.0 * MeV);
  particleGun_->SetParticleMomentumDirection(G4ThreeVector(0.0, 0.0, 1.0));
}

PrimaryGeneratorAction::~PrimaryGeneratorAction()
{
  delete particleGun_;
}

void PrimaryGeneratorAction::GeneratePrimaries(G4Event* event)
{
  // External incident proton source: upstream of the entrance window and device.
  particleGun_->SetParticlePosition(G4ThreeVector(0.0, 0.0, kSourceZ));
  particleGun_->GeneratePrimaryVertex(event);
}
"""


def _action_hh() -> str:
    return r"""
#pragma once

#include "G4VUserActionInitialization.hh"

class ActionInitialization final : public G4VUserActionInitialization {
 public:
  ActionInitialization() = default;
  ~ActionInitialization() override = default;

  void Build() const override;
};
"""


def _action_cc() -> str:
    return r"""
#include "ActionInitialization.hh"
#include "PrimaryGeneratorAction.hh"

void ActionInitialization::Build() const
{
  SetUserAction(new PrimaryGeneratorAction());
}
"""


def _run_macro() -> str:
    return r"""
/control/verbose 1
/run/verbose 1
/event/verbose 0
/tracking/verbose 0
/run/initialize
/run/beamOn 1000
"""


def _init_vis_macro() -> str:
    return r"""
/control/verbose 2
/control/saveHistory
/run/verbose 2
/run/initialize
/control/execute macros/vis.mac
"""


def _vis_macro() -> str:
    return r"""
/vis/open
/vis/viewer/set/autoRefresh false
/vis/verbose errors
/vis/drawVolume
/vis/viewer/set/background 1 1 1
/vis/viewer/set/picking true
/vis/viewer/set/style surface
/vis/viewer/set/auxiliaryEdge true
/vis/viewer/set/viewpointThetaPhi 120 150
/vis/scene/add/scale
/vis/scene/add/axes
/tracking/storeTrajectory 1
/vis/scene/add/trajectories smooth
/vis/modeling/trajectories/create/drawByCharge
/vis/scene/endOfEventAction accumulate
/run/beamOn 100
/vis/viewer/set/autoRefresh true
/vis/verbose warnings
/vis/viewer/flush
"""


def _gui_macro() -> str:
    return r"""
/gui/addMenu run Run
/gui/addButton run "beamOn 1" "/run/beamOn 1"
/gui/addButton run "beamOn 100" "/run/beamOn 100"
/gui/addMenu viewer Viewer
/gui/addButton viewer "Surface" "/vis/viewer/set/style surface"
/gui/addButton viewer "Wireframe" "/vis/viewer/set/style wireframe"
/gui/addButton viewer "Flush" "/vis/viewer/flush"
"""


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    print(create_radagent_visual_smoke_project(args.project_dir))
