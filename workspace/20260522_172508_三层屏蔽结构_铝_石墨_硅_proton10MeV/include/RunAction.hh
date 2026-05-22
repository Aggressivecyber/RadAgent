#ifndef B1RunAction_h
#define B1RunAction_h 1

#include "G4UserRunAction.hh"
#include "G4Accumulable.hh"
#include "G4AccMap.hh"
#include "globals.hh"
#include <fstream>

class G4Run;

namespace B1
{

class RunAction : public G4UserRunAction
{
  public:
    RunAction();
    ~RunAction() override;

    void BeginOfRunAction(const G4Run*) override;
    void EndOfRunAction(const G4Run*) override;

    void AddEdep(G4double edep);
    void AddLayerEdep(const G4String& layerName, G4double edep);

    std::ofstream& GetEventFile() { return fEventFile; }
    std::ofstream& GetStepFile() { return fStepFile; }

  private:
    G4AccValue<G4double> fEdep = 0.;
    G4AccValue<G4double> fEdep2 = 0.;
    G4AccMap<G4String, G4double> fLayerEdep;
    std::ofstream fEventFile;
    std::ofstream fStepFile;
};

}  // namespace B1

#endif
