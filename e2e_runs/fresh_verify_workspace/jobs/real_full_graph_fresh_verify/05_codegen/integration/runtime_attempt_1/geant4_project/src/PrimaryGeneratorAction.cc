//
// Primary generator action implementation.
// Particle type, energy, position and direction are taken directly from
// the G4ModelIR source specification.
//

#include "PrimaryGeneratorAction.hh"

#include "G4ParticleGun.hh"
#include "G4ParticleTable.hh"
#include "G4SystemOfUnits.hh"
#include "G4Event.hh"

PrimaryGeneratorAction::PrimaryGeneratorAction()
  : fParticleGun(nullptr)
{
  // Single particle per event
  G4int nofParticles = 1;
  fParticleGun = new G4ParticleGun(nofParticles);

  // Get particle definition from IR source: "proton"
  G4ParticleDefinition* particleDefinition =
    G4ParticleTable::GetParticleTable()->FindParticle("proton");
  fParticleGun->SetParticleDefinition(particleDefinition);

  // Energy from IR: 10.0 MeV, monoenergetic
  fParticleGun->SetParticleEnergy(10.0 * MeV);

  // Position from IR: (0, 0, -80) mm (source is 80 mm upstream)
  fParticleGun->SetParticlePosition(G4ThreeVector(0.0, 0.0, -80.0 * mm));

  // Direction from IR: (0, 0, 1) - positive z direction
  fParticleGun->SetParticleMomentumDirection(G4ThreeVector(0.0, 0.0, 1.0));

  // No polarization needed for this application
}

PrimaryGeneratorAction::~PrimaryGeneratorAction()
{
  delete fParticleGun;
}

void PrimaryGeneratorAction::GeneratePrimaries(G4Event* anEvent)
{
  // Generate one primary vertex per event
  fParticleGun->GeneratePrimaryVertex(anEvent);
}
