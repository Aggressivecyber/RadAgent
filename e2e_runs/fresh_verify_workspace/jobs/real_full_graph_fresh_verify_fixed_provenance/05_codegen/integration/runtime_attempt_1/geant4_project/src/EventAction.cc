#include "EventAction.hh"
#include "ScoringManager.hh"
#include "OutputManager.hh"
#include "G4Event.hh"
#include "G4RunManager.hh"

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

EventAction::EventAction()
  : G4UserEventAction()
{
}

EventAction::~EventAction() = default;

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void EventAction::BeginOfEventAction(const G4Event*)
{
  auto& scoringMgr = ScoringManager::Instance();
  scoringMgr.BeginOfEvent();
  
  auto* outputMgr = OutputManager::Instance();
  outputMgr->BeginOfEvent();
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void EventAction::EndOfEventAction(const G4Event* event)
{
  G4int eventID = event->GetEventID();
  
  auto& scoringMgr = ScoringManager::Instance();
  scoringMgr.EndOfEvent(eventID);
  
  // Transfer scoring data to output manager
  auto* outputMgr = OutputManager::Instance();
  outputMgr->AddEventScoring(scoringMgr.GetEventEdep(), scoringMgr.GetEventDose());
  outputMgr->EndOfEvent(eventID);
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......