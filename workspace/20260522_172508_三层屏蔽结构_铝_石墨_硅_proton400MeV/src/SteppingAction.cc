#include "SteppingAction.hh"
#include "EventAction.hh"
#include "DetectorConstruction.hh"

#include "G4Step.hh"
#include "G4LogicalVolume.hh"
#include "G4RunManager.hh"
#include "G4SystemOfUnits.hh"
#include "G4VProcess.hh"
#include "G4Track.hh"

namespace B1
{

SteppingAction::SteppingAction(EventAction* eventAction)
  : fEventAction(eventAction)
{}

void SteppingAction::UserSteppingAction(const G4Step* step)
{
  // 延迟初始化: 第一次 stepping 时从 DetectorConstruction 获取 volumes
  if (fScoringVolumes.empty()) {
    const auto* det = static_cast<const DetectorConstruction*>(
      G4RunManager::GetRunManager()->GetUserDetectorConstruction());
    if (det) {
      fScoringVolumes = det->GetLayerVolumes();
    }
  }

  G4LogicalVolume* volume = step->GetPreStepPoint()
      ->GetTouchableHandle()->GetVolume()->GetLogicalVolume();
  G4double edep = step->GetTotalEnergyDeposit();

  // 逐层累加
  for (auto* sv : fScoringVolumes) {
    if (volume == sv) {
      fEventAction->AddEdep(edep);
      fEventAction->AddLayerEdep(volume->GetName(), edep);
      break;
    }
  }

  // 记录逐步数据
  auto* track = step->GetTrack();
  auto* prePoint = step->GetPreStepPoint();
  auto* postPoint = step->GetPostStepPoint();

  StepRecord rec;
  rec.particle_name = track->GetParticleDefinition()->GetParticleName();
  rec.kinetic_energy = prePoint->GetKineticEnergy() / MeV;
  rec.x = prePoint->GetPosition().x() / cm;
  rec.y = prePoint->GetPosition().y() / cm;
  rec.z = prePoint->GetPosition().z() / cm;
  rec.volume_name = volume->GetName();
  rec.edep = edep / MeV;
  rec.step_length = step->GetStepLength() / mm;

  // 获取物理过程名
  if (postPoint->GetProcessDefinedStep()) {
    rec.process_name = postPoint->GetProcessDefinedStep()->GetProcessName();
  } else {
    rec.process_name = "none";
  }

  fEventAction->AddStep(rec);
}

}  // namespace B1
