#include "ActionInitialization.hh"
#include "DetectorConstruction.hh"
#include "PrimaryGeneratorAction.hh"
#include "RunAction.hh"
#include "EventAction.hh"
#include "SteppingAction.hh"

namespace B1
{

void ActionInitialization::BuildForMaster() const
{
  SetUserAction(new RunAction());
}

void ActionInitialization::Build() const
{
  auto* runAction = new RunAction();
  auto* eventAction = new EventAction(runAction);
  auto* steppingAction = new SteppingAction(eventAction);
  auto* generator = new PrimaryGeneratorAction();

  SetUserAction(runAction);
  SetUserAction(eventAction);
  SetUserAction(steppingAction);
  SetUserAction(generator);
}

}  // namespace B1
