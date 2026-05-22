#include "PrimaryGeneratorAction.hh"

#include "G4Box.hh"
#include "G4IonTable.hh"
#include "G4LogicalVolume.hh"
#include "G4LogicalVolumeStore.hh"
#include "G4ParticleGun.hh"
#include "G4ParticleTable.hh"
#include "G4SystemOfUnits.hh"
#include "Randomize.hh"

#include <algorithm>

namespace B1
{

PrimaryGeneratorAction::PrimaryGeneratorAction()
{
  G4int n_particle = 1;
  fParticleGun = new G4ParticleGun(n_particle);

  G4ParticleTable* particleTable = G4ParticleTable::GetParticleTable();
  G4String particleName;
  fParticleGun->SetParticleDefinition(particleTable->FindParticle(particleName = "e-"));


  fParticleGun->SetParticleMomentumDirection(G4ThreeVector(0, 0, -1));
  fParticleGun->SetParticleEnergy(2.0 * MeV);
}

PrimaryGeneratorAction::~PrimaryGeneratorAction()
{
  delete fParticleGun;
}

void PrimaryGeneratorAction::GeneratePrimaries(G4Event* event)
{
  // Ion lazy init (GetIon only works after G4RunManager::Initialize)
  if (fIonNeedsInit) {
    auto ionTable = G4ParticleTable::GetParticleTable()->GetIonTable();
    fParticleGun->SetParticleDefinition(ionTable->GetIon(fIonZ, fIonA));
    fIonNeedsInit = false;
  }

  // Energy spectrum sampling (CDF inverse transform)
  if (fUseSpectrum && fEnergyCDF.size() > 1) {
    G4double r = G4UniformRand();
    auto it = std::lower_bound(fEnergyCDF.begin(), fEnergyCDF.end(), r);
    size_t idx = std::distance(fEnergyCDF.begin(), it);
    if (idx > 0) idx--;
    if (idx >= fEnergyValues.size()) idx = fEnergyValues.size() - 1;
    fParticleGun->SetParticleEnergy(fEnergyValues[idx] * MeV);
  }

  // Direction sampling
  if (fIsotropic) {
    G4double cosTheta = 2.0 * G4UniformRand() - 1.0;
    G4double sinTheta = std::sqrt(1.0 - cosTheta * cosTheta);
    G4double phi = 2.0 * CLHEP::pi * G4UniformRand();
    fParticleGun->SetParticleMomentumDirection(
      G4ThreeVector(sinTheta * std::cos(phi), sinTheta * std::sin(phi), cosTheta));
  } else if (fHemisphere) {
    G4double cosTheta = G4UniformRand();
    G4double sinTheta = std::sqrt(1.0 - cosTheta * cosTheta);
    G4double phi = 2.0 * CLHEP::pi * G4UniformRand();
    fParticleGun->SetParticleMomentumDirection(
      G4ThreeVector(sinTheta * std::cos(phi), sinTheta * std::sin(phi), -cosTheta));
  }

  G4double envSizeXY = 0;
  G4double envSizeZ = 0;

  if (!fEnvelopeBox) {
    G4LogicalVolume* envLV = G4LogicalVolumeStore::GetInstance()->GetVolume("World");
    if (envLV) fEnvelopeBox = dynamic_cast<G4Box*>(envLV->GetSolid());
  }

  if (fEnvelopeBox) {
    envSizeXY = fEnvelopeBox->GetXHalfLength() * 2.;
    envSizeZ = fEnvelopeBox->GetZHalfLength() * 2.;
  }

  G4double size = 0.8;
  G4double x0 = size * envSizeXY * (G4UniformRand() - 0.5);
  G4double y0 = size * envSizeXY * (G4UniformRand() - 0.5);
  G4double z0 = 0.5 * envSizeZ;

  fParticleGun->SetParticlePosition(G4ThreeVector(x0, y0, z0));
  fParticleGun->GeneratePrimaryVertex(event);
}

}  // namespace B1
