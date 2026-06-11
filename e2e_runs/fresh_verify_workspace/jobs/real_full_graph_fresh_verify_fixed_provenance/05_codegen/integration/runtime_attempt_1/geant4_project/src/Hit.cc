// Hit.cc
// Implementation of Hit class for sensitive detector measurements

#include "Hit.hh"
#include "G4UnitsTable.hh"
#include "G4VisAttributes.hh"
#include "G4Colour.hh"
#include "G4Circle.hh"
#include "G4VVisManager.hh"
#include "G4VMarker.hh"

G4ThreadLocal G4Allocator<Hit>* HitAllocator = nullptr;

namespace {
constexpr G4double kHitMarkerScreenSize = 5.0;
constexpr int kHitPrintWidth = 7;
}



//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

G4bool Hit::operator==(const Hit& right) const
{
    return (this == &right) ? true : false;
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void Hit::Draw()
{
    auto visAttributes = new G4VisAttributes(G4Colour::Red());
    visAttributes->SetVisibility(true);
    visAttributes->SetForceSolid(true);
    
    G4VVisManager* pVVisManager = G4VVisManager::GetConcreteInstance();
    if (pVVisManager) {
        G4Circle circle(fPos);
        circle.SetScreenSize(kHitMarkerScreenSize);
        circle.SetFillStyle(G4VMarker::filled);
        circle.SetVisAttributes(visAttributes);
        pVVisManager->Draw(circle);
    }
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void Hit::Print()
{
    G4cout << "  TrackID: " << fTrackID
           << "  Energy deposition: " << std::setw(kHitPrintWidth) << G4BestUnit(fEdep, "Energy")
           << "  Position: " << std::setw(kHitPrintWidth) << G4BestUnit(fPos, "Length")
           << G4endl;
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......
