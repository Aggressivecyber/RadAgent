#include "ActionInitialization.hh"
#include "PrimaryGeneratorAction.hh"
#include "RunAction.hh"
#include "EventAction.hh"
#include "SteppingAction.hh"

ActionInitialization::ActionInitialization()
  : G4VUserActionInitialization()
{
}

ActionInitialization::~ActionInitialization() = default;

void ActionInitialization::BuildForMaster() const
{
  // In multithreaded mode, only RunAction runs on the master thread
  SetUserAction(new RunAction());
}

void ActionInitialization::Build() const
{
  SetUserAction(new PrimaryGeneratorAction());
  SetUserAction(new RunAction());
  SetUserAction(new EventAction());
  SetUserAction(new SteppingAction());
}
