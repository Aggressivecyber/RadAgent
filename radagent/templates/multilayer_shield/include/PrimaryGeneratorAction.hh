#ifndef PrimaryGeneratorAction_h
#define PrimaryGeneratorAction_h 1

#include "G4VUserPrimaryGeneratorAction.hh"
#include "globals.hh"

#include <vector>

class G4ParticleGun;
class G4Box;
class G4Event;

namespace B1
{

class PrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction
{
  public:
    PrimaryGeneratorAction();
    ~PrimaryGeneratorAction() override;

    void GeneratePrimaries(G4Event*) override;

  private:
    G4ParticleGun* fParticleGun = nullptr;
    G4Box* fEnvelopeBox = nullptr;
    // Ion lazy init
    G4bool fIonNeedsInit = false;
    G4int fIonZ = 0;
    G4int fIonA = 0;
    // Energy spectrum (CDF inverse sampling)
    G4bool fUseSpectrum = false;
    std::vector<G4double> fEnergyValues;
    std::vector<G4double> fEnergyCDF;
    // Direction mode
    G4bool fIsotropic = false;
    G4bool fHemisphere = false;
};

}  // namespace B1

#endif
