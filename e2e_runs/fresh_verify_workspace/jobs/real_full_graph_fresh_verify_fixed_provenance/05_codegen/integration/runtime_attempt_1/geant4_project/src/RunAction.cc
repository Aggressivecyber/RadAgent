#include "RunAction.hh"
#include "ScoringManager.hh"
#include "OutputManager.hh"
#include "G4Run.hh"
#include "G4RunManager.hh"
#include "G4UnitsTable.hh"
#include "G4SystemOfUnits.hh"

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

RunAction::RunAction()
  : G4UserRunAction()
{
}

RunAction::~RunAction() = default;

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void RunAction::BeginOfRunAction(const G4Run*)
{
  // Inform runManager to save random number seed
  G4RunManager::GetRunManager()->SetRandomNumberStore(false);
  
  // Initialize scoring manager
  auto& scoringMgr = ScoringManager::Instance();
  scoringMgr.BeginOfRun();
  
  // Initialize output manager
  auto* outputMgr = OutputManager::Instance();
  outputMgr->BeginOfRun();
  
  G4cout << "==== Run Started ====" << G4endl;
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void RunAction::EndOfRunAction(const G4Run*)
{
  // Finalize scoring manager
  auto& scoringMgr = ScoringManager::Instance();
  scoringMgr.EndOfRun();
  
  // Finalize output manager (writes all artifacts)
  auto* outputMgr = OutputManager::Instance();
  outputMgr->EndOfRun();
  
  G4cout << "==== Run Ended ====" << G4endl;
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......