#include "DetectorConstruction.hh"
#include "PhysicsListFactoryWrapper.hh"
#include "ActionInitialization.hh"
#include "ScoringManager.hh"
#include "OutputManager.hh"

#include "G4RunManagerFactory.hh"
#include "G4SteppingVerbose.hh"
#include "G4UIExecutive.hh"
#include "G4UImanager.hh"
#include "G4VisExecutive.hh"
#include "G4SystemOfUnits.hh"

int main(int argc, char** argv)
{
  constexpr G4int kSteppingVerbosePrecision = 4;
  // Set default output directory if not already set
  if (std::getenv("G4_OUTPUT_DIR") == nullptr) {
#ifdef _WIN32
    _putenv_s("G4_OUTPUT_DIR", "output");
#else
    setenv("G4_OUTPUT_DIR", "output", 0);
#endif
  }

  // Detect interactive mode (no arguments) and define UI session
  G4UIExecutive* ui = nullptr;
  if (argc == 1) {
    ui = new G4UIExecutive(argc, argv);
  }

  // Use best unit stepping verbose
  G4SteppingVerbose::UseBestUnit(kSteppingVerbosePrecision);

  // Construct the default run manager
  auto* runManager =
      G4RunManagerFactory::CreateRunManager(G4RunManagerType::Serial);

  // Set mandatory initialization classes
  runManager->SetUserInitialization(new DetectorConstruction());

  PhysicsListFactoryWrapper physicsFactory;
  runManager->SetUserInitialization(physicsFactory.CreatePhysicsList());

  runManager->SetUserInitialization(new ActionInitialization());

  // Initialize visualization with the default graphics system
  auto* visManager = new G4VisExecutive(argc, argv);
  visManager->Initialize();

  // Get the pointer to the User Interface manager
  auto* UImanager = G4UImanager::GetUIpointer();

  if (ui) {
    // Interactive mode: execute init.mac then start UI session
    UImanager->ApplyCommand("/control/execute macros/init.mac");
    ui->SessionStart();
    delete ui;
  }
  else {
    // Batch mode: execute macro provided as command-line argument
    G4String command = "/control/execute ";
    G4String fileName = argv[1];
    UImanager->ApplyCommand(command + fileName);
  }

  // Job termination
  delete visManager;
  delete runManager;

  return 0;
}
