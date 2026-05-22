#include "ActionInitialization.hh"
#include "DetectorConstruction.hh"
#include "QBBC.hh"

#include "G4RunManagerFactory.hh"
#include "G4SteppingVerbose.hh"
#include "G4UIExecutive.hh"
#include "G4UImanager.hh"
#include "G4Trajectory.hh"
#include "G4TrajectoryContainer.hh"
#include "G4ios.hh"

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

  auto physicsList = new QBBC;
  physicsList->SetVerboseLevel(0);
  runManager->SetUserInitialization(physicsList);

  runManager->SetUserInitialization(new ActionInitialization());

  // 启用轨迹记录（用于粒子径迹分析和可视化）
  // 通过 UI command 在 run.mac 中控制: /tracking/storeTrajectory 1

  if (!ui) {
    G4String command = "/control/execute ";
    G4String fileName = argv[1];
    auto UImanager = G4UImanager::GetUIpointer();
    UImanager->ApplyCommand(command + fileName);
  } else {
    auto UImanager = G4UImanager::GetUIpointer();
    UImanager->ApplyCommand("/run/initialize");
    UImanager->ApplyCommand("/run/beamOn 100000");
    delete ui;
  }

  delete runManager;
}
