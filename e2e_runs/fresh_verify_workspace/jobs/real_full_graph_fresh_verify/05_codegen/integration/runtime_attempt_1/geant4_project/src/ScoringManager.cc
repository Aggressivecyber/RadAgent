namespace {
constexpr int kCsvPrecision = 6;
}

// ScoringManager.cc
// Implementation of energy deposition and dose scoring for silicon detector

#include "ScoringManager.hh"
#include "G4LogicalVolume.hh"
#include "G4Material.hh"
#include "G4VSolid.hh"
#include "G4SystemOfUnits.hh"
#include "G4UnitsTable.hh"
#include "G4Exception.hh"
#include <iostream>
#include <iomanip>

ScoringManager& ScoringManager::Instance()
{
    static ScoringManager instance;
    return instance;
}

ScoringManager::ScoringManager()
    : fScoringVolume(nullptr),
      fVolume(0.0),
      fDensity(0.0),
      fMass(0.0),
      fEventEdep(0.0),
      fEventDose(0.0),
      fTotalEdep(0.0),
      fTotalDose(0.0),
      fEventCount(0),
      fCSVOutput(true)
{
}

ScoringManager::~ScoringManager()
{
    if (fOutputFile.is_open()) {
        fOutputFile.close();
    }
}

void ScoringManager::Initialize(G4LogicalVolume* scoringVolume)
{
    fScoringVolume = scoringVolume;
    if (!fScoringVolume) {
        G4ExceptionDescription msg;
        msg << "Scoring volume is null. Scoring will not be active.";
        G4Exception("ScoringManager::Initialize", "ScoringMgr001",
                    JustWarning, msg);
        return;
    }

    // Get volume from solid (use const_cast since GetCubicVolume is not const-qualified)
    const G4VSolid* solid = fScoringVolume->GetSolid();
    fVolume = const_cast<G4VSolid*>(solid)->GetCubicVolume(); // mm^3
    fVolume /= (cm * cm * cm); // convert to cubic centimeters

    // Get density from material
    fDensity = fScoringVolume->GetMaterial()->GetDensity() / (g / cm3); // g/cubic centimeters

    // Calculate mass in kg
    fMass = fVolume * fDensity * g / kg; // kg

    G4cout << "ScoringManager initialized:" << G4endl
           << "  Volume: " << fVolume << " cubic centimeters" << G4endl
           << "  Density: " << fDensity << " g/cubic centimeters" << G4endl
           << "  Mass: " << fMass << " kg" << G4endl;
}

void ScoringManager::RecordEnergyDeposit(G4double edep)
{
    fEventEdep += edep;
}

void ScoringManager::BeginOfEvent()
{
    fEventEdep = 0.0;
    fEventDose = 0.0;
}

void ScoringManager::EndOfEvent(G4int eventId)
{
    // Calculate dose for this event
    fEventDose = CalculateDose(fEventEdep);

    // Update run totals
    fTotalEdep += fEventEdep;
    fTotalDose += fEventDose;
    fEventCount++;

    // Write event data to CSV
    if (fCSVOutput) {
        WriteEventToCSV(eventId);
    }
}

void ScoringManager::BeginOfRun()
{
    fTotalEdep = 0.0;
    fTotalDose = 0.0;
    fEventCount = 0;

    if (fCSVOutput) {
        fOutputFile.open(fOutputFileName);
        if (fOutputFile.is_open()) {
            fOutputFile << "EventID,edep_MeV,dose_Gy" << std::endl;
        }
    }
}

void ScoringManager::EndOfRun()
{
    WriteRunSummary();
}

G4double ScoringManager::CalculateDose(G4double edep) const
{
    if (fMass <= 0.0) return 0.0;

    // Convert edep from MeV to Joules
    G4double edep_J = edep * MeV / joule;

    // Dose = energy / mass (Gy = J/kg)
    G4double dose = edep_J / fMass;

    return dose;
}

void ScoringManager::WriteEventToCSV(G4int eventId)
{
    if (fOutputFile.is_open()) {
        fOutputFile << eventId << ","
                    << std::scientific << std::setprecision(kCsvPrecision)
                    << fEventEdep / MeV << ","
                    << fEventDose / gray
                    << std::endl;
    }
}

void ScoringManager::WriteRunSummary()
{
    if (fOutputFile.is_open()) {
        fOutputFile.close();
    }

    G4cout << G4endl
           << "=================== Scoring Summary ===================" << G4endl
           << "  Total events: " << fEventCount << G4endl
           << "  Total energy deposited: " << G4BestUnit(fTotalEdep, "Energy") << G4endl
           << "  Average dose per event: ";
    if (fEventCount > 0) {
        G4cout << fTotalDose / fEventCount / gray << " Gy";
    } else {
        G4cout << "0 Gy";
    }
    G4cout << G4endl
           << "=====================================================" << G4endl;
}
