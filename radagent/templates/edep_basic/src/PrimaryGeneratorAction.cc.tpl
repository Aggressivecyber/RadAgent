#include "PrimaryGeneratorAction.hh"

#include "G4Box.hh"
#include "G4LogicalVolume.hh"
#include "G4LogicalVolumeStore.hh"
#include "G4ParticleGun.hh"
#include "G4ParticleTable.hh"
#include "G4SystemOfUnits.hh"
#include "Randomize.hh"

namespace B1
{

PrimaryGeneratorAction::PrimaryGeneratorAction()
{
  G4int n_particle = 1;
  fParticleGun = new G4ParticleGun(n_particle);

  G4ParticleTable* particleTable = G4ParticleTable::GetParticleTable();
  G4String particleName;
  G4ParticleDefinition* particle = particleTable->FindParticle(particleName = "$PARTICLE_TYPE");
  fParticleGun->SetParticleDefinition(particle);
  fParticleGun->SetParticleMomentumDirection(G4ThreeVector($BEAM_DIRECTION_X, $BEAM_DIRECTION_Y, $BEAM_DIRECTION_Z));
  fParticleGun->SetParticleEnergy($PARTICLE_ENERGY * $PARTICLE_ENERGY_UNIT);
}

PrimaryGeneratorAction::~PrimaryGeneratorAction()
{
  delete fParticleGun;
}

void PrimaryGeneratorAction::GeneratePrimaries(G4Event* event)
{
  G4double envSizeXY = 0;
  G4double envSizeZ = 0;

  if (!fEnvelopeBox) {
    G4LogicalVolume* envLV = G4LogicalVolumeStore::GetInstance()->GetVolume("Envelope");
    if (envLV) fEnvelopeBox = dynamic_cast<G4Box*>(envLV->GetSolid());
  }

  if (fEnvelopeBox) {
    envSizeXY = fEnvelopeBox->GetXHalfLength() * 2.;
    envSizeZ = fEnvelopeBox->GetZHalfLength() * 2.;
  }

  G4double size = 0.8;
  G4double x0 = size * envSizeXY * (G4UniformRand() - 0.5);
  G4double y0 = size * envSizeXY * (G4UniformRand() - 0.5);
  G4double z0 = -0.5 * envSizeZ;

  fParticleGun->SetParticlePosition(G4ThreeVector(x0, y0, z0));
  fParticleGun->GeneratePrimaryVertex(event);
}

}  // namespace B1
