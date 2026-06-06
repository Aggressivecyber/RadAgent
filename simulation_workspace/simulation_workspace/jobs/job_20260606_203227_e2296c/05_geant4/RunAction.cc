#include "RunAction.hh"
#include "DetectorConstruction.hh"
#include "VoxelScorer.hh"
#include "G4Run.hh"
#include "G4SystemOfUnits.hh"
#include "G4Material.hh"
#include <sys/stat.h>

RunAction::RunAction(DetectorConstruction* det)
  : G4UserRunAction(),
    fDetector(det)
{}

RunAction::~RunAction()
{}

void RunAction::BeginOfRunAction(const G4Run* run) {
  G4cout << "Starting run " << run->GetRunID() << G4endl;

  // Initialize voxel scorer with target parameters
  VoxelScorer* scorer = VoxelScorer::GetInstance();
  scorer->Initialize(
    fDetector->GetVoxelSize(),
    fDetector->GetTargetSizeX(),
    fDetector->GetTargetSizeY(),
    fDetector->GetTargetSizeZ(),
    fDetector->GetTargetMaterial()
  );
}

void RunAction::EndOfRunAction(const G4Run* run) {
  G4cout << "End of run " << run->GetRunID() << G4endl;
  G4double nEvents = run->GetNumberOfEvent();
  G4cout << "Processed " << nEvents << " events." << G4endl;

  // Write scoring to CSV
  G4String outputDir = "simulation_workspace/jobs/job_20260606_203227_e2296c/05_geant4/output";
  // Create directory if it doesn't exist (simple: assume exists or use mkdir)
  mkdir(outputDir.c_str(), 0755); // on POSIX; for more portability, use G4 filesystem? Minimal.
  VoxelScorer* scorer = VoxelScorer::GetInstance();
  scorer->WriteCSV(outputDir);
}
