// ScoringManager.hh
// Manages energy deposition and dose scoring for silicon detector
// Provides dose calculation based on geometry and material properties

#ifndef SCORING_MANAGER_HH
#define SCORING_MANAGER_HH

#include "G4LogicalVolume.hh"
#include "G4Material.hh"
#include "G4SystemOfUnits.hh"
#include "globals.hh"
#include <vector>
#include <fstream>

class ScoringManager
{
public:
    static ScoringManager& Instance();

    // Initialize with scoring volume
    void Initialize(G4LogicalVolume* scoringVolume);

    // Energy deposition recording
    void RecordEnergyDeposit(G4double edep);

    // Event management
    void BeginOfEvent();
    void EndOfEvent(G4int eventId);

    // Run management
    void BeginOfRun();
    void EndOfRun();

    // Data access
    G4double GetEventEdep() const { return fEventEdep; }
    G4double GetEventDose() const { return fEventDose; }
    G4double GetTotalEdep() const { return fTotalEdep; }
    G4double GetTotalDose() const { return fTotalDose; }
    G4int GetEventCount() const { return fEventCount; }

    // Output control
    void SetOutputFileName(const G4String& filename) { fOutputFileName = filename; }
    void EnableCSVOutput(G4bool enable) { fCSVOutput = enable; }

private:
    ScoringManager();
    ~ScoringManager();

    // Prevent copying
    ScoringManager(const ScoringManager&) = delete;
    ScoringManager& operator=(const ScoringManager&) = delete;

    // Dose calculation
    G4double CalculateDose(G4double edep) const;

    // Output methods
    void WriteEventToCSV(G4int eventId);
    void WriteRunSummary();

    // Geometry and material information
    G4LogicalVolume* fScoringVolume = nullptr;
    G4double fVolume = 0.0;  // in cubic centimeters
    G4double fDensity = 0.0; // in g/cubic centimeters
    G4double fMass = 0.0;    // in kg

    // Current event data
    G4double fEventEdep = 0.0;  // in MeV
    G4double fEventDose = 0.0;  // in Gy

    // Run totals
    G4double fTotalEdep = 0.0;  // in MeV
    G4double fTotalDose = 0.0;  // in Gy
    G4int fEventCount = 0;

    // Output control
    G4String fOutputFileName = "scoring.csv";
    G4bool fCSVOutput = true;
    std::ofstream fOutputFile;
};

#endif // SCORING_MANAGER_HH