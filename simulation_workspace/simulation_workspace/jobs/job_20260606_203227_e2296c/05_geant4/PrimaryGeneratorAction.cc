#include "PrimaryGeneratorAction.hh"
#include "G4Event.hh"
#include "G4ParticleTable.hh"
#include "G4ParticleDefinition.hh"
#include "G4SystemOfUnits.hh"

PrimaryGeneratorAction::PrimaryGeneratorAction()
  : G4VUserPrimaryGeneratorAction(),
    fParticleGun(nullptr)
{
  G4int nParticles = 1;
  fParticleGun = new G4ParticleGun(nParticles);

  // Proton
  G4ParticleDefinition* proton = G4ParticleTable::GetParticleTable()->FindParticle("proton");
  fParticleGun->SetParticleDefinition(proton);

  // Energy 10 MeV
  fParticleGun->SetParticleEnergy(10.0 * MeV);

  // Direction +z
  fParticleGun->SetParticleMomentumDirection(G4ThreeVector(0., 0., 1.));

  // Position at center of target on -Z face (just outside to enter)
  // Target extends from -500 um to +500 um in X/Y, -150 to +150 in Z.
  // Place source at (0,0,-160 um) to just outside.
  fParticleGun->SetParticlePosition(G4ThreeVector(0., 0., -160.0 * um));
}

PrimaryGeneratorAction::~PrimaryGeneratorAction() {
  delete fParticleGun;
}

void PrimaryGeneratorAction::GeneratePrimaries(G4Event* anEvent) {
  fParticleGun->GeneratePrimaryVertex(anEvent);
}
