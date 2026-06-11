// SensitiveDetector.hh
// Sensitive detector for silicon detector energy deposition measurement
// Links to DetectorConstruction geometry and ScoringManager for dose calculation

#ifndef SENSITIVE_DETECTOR_HH
#define SENSITIVE_DETECTOR_HH

#include "G4VSensitiveDetector.hh"
#include "Hit.hh"
#include "globals.hh"
#include <vector>

class G4Step;
class G4HCofThisEvent;
class G4TouchableHistory;

class ScoringManager;

class SensitiveDetector : public G4VSensitiveDetector
{
public:
    SensitiveDetector(const G4String& name, const G4String& hitsCollectionName);
    ~SensitiveDetector() override = default;

    // Methods from base class
    void Initialize(G4HCofThisEvent* hce) override;
    G4bool ProcessHits(G4Step* step, G4TouchableHistory* history) override;
    void EndOfEvent(G4HCofThisEvent* hce) override;

    // Access to hit collection
    HitsCollection* GetHitsCollection() const { return fHitsCollection; }

private:
    HitsCollection* fHitsCollection = nullptr;
    ScoringManager* fScoringManager = nullptr;
};

#endif // SENSITIVE_DETECTOR_HH