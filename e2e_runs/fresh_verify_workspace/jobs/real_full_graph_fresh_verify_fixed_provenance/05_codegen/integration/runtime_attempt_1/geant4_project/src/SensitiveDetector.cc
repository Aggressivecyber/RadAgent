// SensitiveDetector.cc
// Implementation of sensitive detector for silicon detector energy measurement

#include "SensitiveDetector.hh"
#include "ScoringManager.hh"
#include "Hit.hh"

#include "G4HCofThisEvent.hh"
#include "G4Step.hh"
#include "G4SDManager.hh"
#include "G4TouchableHistory.hh"
#include "G4Track.hh"
#include "G4UnitsTable.hh"

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

SensitiveDetector::SensitiveDetector(const G4String& name,
                                     const G4String& hitsCollectionName)
    : G4VSensitiveDetector(name)
{
    collectionName.insert(hitsCollectionName);
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void SensitiveDetector::Initialize(G4HCofThisEvent* hce)
{
    // Create hits collection
    fHitsCollection =
        new HitsCollection(SensitiveDetectorName, collectionName[0]);

    // Add this collection to hce
    G4int hcID =
        G4SDManager::GetSDMpointer()->GetCollectionID(collectionName[0]);
    hce->AddHitsCollection(hcID, fHitsCollection);

    // Get scoring manager instance
    fScoringManager = &ScoringManager::Instance();
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory*)
{
    // Get energy deposition
    G4double edep = step->GetTotalEnergyDeposit();

    // Only record hits with energy deposition
    if (edep == 0.0) return false;

    // Create new hit
    ::Hit* hit = new ::Hit();

    // Set hit properties
    hit->SetTrackID(step->GetTrack()->GetTrackID());
    hit->SetEdep(edep);
    hit->SetPos(step->GetPostStepPoint()->GetPosition());
    hit->SetLocalPos(
        step->GetPreStepPoint()->GetTouchableHandle()
            ->GetHistory()->GetTopTransform().TransformPoint(
                step->GetPostStepPoint()->GetPosition()));

    // Add to collection
    fHitsCollection->insert(hit);

    // Record energy deposition in scoring manager
    fScoringManager->RecordEnergyDeposit(edep);

    return true;
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void SensitiveDetector::EndOfEvent(G4HCofThisEvent*)
{
    if (verboseLevel > 1) {
        G4int nofHits = fHitsCollection->entries();
        G4cout << G4endl
               << "-------->Hits Collection: in this event they are "
               << nofHits
               << " hits in the silicon detector: " << G4endl;
        for (G4int i = 0; i < nofHits; i++)
            (*fHitsCollection)[i]->Print();
    }
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......
