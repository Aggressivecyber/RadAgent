// PhysicsListFactoryWrapper.cc
// Implementation of physics list factory

#include "PhysicsListFactoryWrapper.hh"
#include "G4SystemOfUnits.hh"

#include "G4PhysListFactory.hh"
#include "G4VModularPhysicsList.hh"

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

PhysicsListFactoryWrapper::PhysicsListFactoryWrapper() = default;

PhysicsListFactoryWrapper::~PhysicsListFactoryWrapper() = default;

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

G4VUserPhysicsList* PhysicsListFactoryWrapper::CreatePhysicsList()
{
  // Use Geant4 reference physics list factory
  G4PhysListFactory factory;
  
  // Create QGSP_BIC physics list - suitable for hadron therapy and general purpose
  // physics at intermediate energies (includes electromagnetic and hadronic physics)
  G4VModularPhysicsList* physicsList = factory.GetReferencePhysList("FTFP_BERT");
  
  // Set default production cuts
  physicsList->SetDefaultCutValue(0.1 * mm);
  
  // Set verbosity level
  physicsList->SetVerboseLevel(0);
  
  return physicsList;
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......