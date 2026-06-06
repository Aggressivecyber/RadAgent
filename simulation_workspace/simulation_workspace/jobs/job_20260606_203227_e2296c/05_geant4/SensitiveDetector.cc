#include "SensitiveDetector.hh"
#include "G4Step.hh"
#include "G4Track.hh"
#include "G4SystemOfUnits.hh"
#include "VoxelScorer.hh"

SensitiveDetector::SensitiveDetector(const G4String& name)
  : G4VSensitiveDetector(name),
    fVoxelSize(0.),
    fTargetSizeX(0.), fTargetSizeY(0.), fTargetSizeZ(0.)
{}

SensitiveDetector::~SensitiveDetector()
{}

void SensitiveDetector::SetVoxelParams(G4double voxelSize, G4double sizeX, G4double sizeY, G4double sizeZ) {
  fVoxelSize = voxelSize;
  fTargetSizeX = sizeX;
  fTargetSizeY = sizeY;
  fTargetSizeZ = sizeZ;
}

void SensitiveDetector::Initialize(G4HCofThisEvent*)
{
  // No hits collections used, we accumulate directly in VoxelScorer
}

G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory*)
{
  G4double edep = step->GetTotalEnergyDeposit();
  if (edep <= 0.) return false;

  G4StepPoint* preStepPoint = step->GetPreStepPoint();
  G4ThreeVector pos = preStepPoint->GetPosition();

  // Add to scoring
  VoxelScorer* scorer = VoxelScorer::GetInstance();
  scorer->AddEdep(pos, edep);

  return true;
}
