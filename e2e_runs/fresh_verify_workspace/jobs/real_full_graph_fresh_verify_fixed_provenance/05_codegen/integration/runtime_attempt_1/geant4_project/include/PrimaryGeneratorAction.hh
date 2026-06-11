#ifndef PrimaryGeneratorAction_h
#define PrimaryGeneratorAction_h 1

#include "G4VUserPrimaryGeneratorAction.hh"
#include "G4ThreeVector.hh"
#include "globals.hh"

class G4ParticleGun;
class G4Event;

/// Primary generator action class using a particle gun.
/// Configures particle type, energy, position and direction from G4ModelIR.

class PrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction
{
public:
  PrimaryGeneratorAction();
  ~PrimaryGeneratorAction() override;

  void GeneratePrimaries(G4Event* event) override;

  const G4ParticleGun* GetParticleGun() const { return fParticleGun; }

private:
  G4ParticleGun* fParticleGun;
};

#endif
