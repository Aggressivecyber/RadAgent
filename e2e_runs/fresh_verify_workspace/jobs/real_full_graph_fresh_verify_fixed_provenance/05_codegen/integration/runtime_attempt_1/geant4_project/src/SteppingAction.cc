#include "SteppingAction.hh"
#include "ScoringManager.hh"
#include "OutputManager.hh"
#include "G4Step.hh"
#include "G4Track.hh"
#include "G4StepPoint.hh"
#include "G4LogicalVolume.hh"
#include "G4LogicalVolumeStore.hh"
#include "G4SystemOfUnits.hh"

SteppingAction::SteppingAction()
  : G4UserSteppingAction()
{
}

SteppingAction::~SteppingAction() = default;

void SteppingAction::SetScoringVolume(G4LogicalVolume* lv)
{
  fScoringVolume = lv;
}

void SteppingAction::UserSteppingAction(const G4Step* step)
{
  // Lazy-initialize scoring volume from DetectorConstruction
  if (fScoringVolume == nullptr) {
    auto* store = G4LogicalVolumeStore::GetInstance();
    auto it = store->GetVolume("SiliconDetector");
    if (it != nullptr) {
      fScoringVolume = it;
    }
  }

  // Only process steps in the scoring volume
  G4LogicalVolume* preVol = step->GetPreStepPoint()->GetTouchableHandle()
                                        ->GetVolume()->GetLogicalVolume();
  if (preVol != fScoringVolume) return;

  G4double edep = step->GetTotalEnergyDeposit();
  if (edep <= 0.0) return;

  // Record energy deposit and dose to ScoringManager

  // Record 3D hit position and energy to OutputManager for mesh generation
  G4ThreeVector pos = step->GetPreStepPoint()->GetPosition();
  OutputManager::Instance()->Record3DHit(pos, edep / MeV);
}
