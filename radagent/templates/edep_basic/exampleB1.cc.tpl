#include "ActionInitialization.hh"
#include "DetectorConstruction.hh"
#include "$PHYSICS_LIST_INCLUDE"

#include "G4RunManagerFactory.hh"
#include "G4SteppingVerbose.hh"
#include "G4UIExecutive.hh"
#include "G4UImanager.hh"

using namespace B1;

int main(int argc, char** argv)
{
  G4UIExecutive* ui = nullptr;
  if (argc == 1) {
    ui = new G4UIExecutive(argc, argv);
  }

  G4int precision = 4;
  G4SteppingVerbose::UseBestUnit(precision);

  auto runManager = G4RunManagerFactory::CreateRunManager(G4RunManagerType::Default);

  runManager->SetUserInitialization(new DetectorConstruction());

  auto physicsList = new $PHYSICS_LIST_CLASS;
  physicsList->SetVerboseLevel(0);
  runManager->SetUserInitialization(physicsList);

  runManager->SetUserInitialization(new ActionInitialization());

  if (!ui) {
    G4String command = "/control/execute ";
    G4String fileName = argv[1];
    auto UImanager = G4UImanager::GetUIpointer();
    UImanager->ApplyCommand(command + fileName);
  } else {
    auto UImanager = G4UImanager::GetUIpointer();
    UImanager->ApplyCommand("/run/initialize");
    UImanager->ApplyCommand("/run/beamOn $NUM_EVENTS");
    delete ui;
  }

  delete runManager;
}
