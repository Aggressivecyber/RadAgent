#ifndef B1EventAction_h
#define B1EventAction_h 1

#include "G4UserEventAction.hh"
#include "globals.hh"
#include <map>
#include <vector>

class G4Event;

namespace B1
{

class RunAction;

struct StepRecord {
    G4double kinetic_energy = 0.;    // MeV
    G4double x = 0., y = 0., z = 0.;  // cm
    G4String volume_name;
    G4String particle_name;
    G4double edep = 0.;              // MeV
    G4double step_length = 0.;       // mm
    G4String process_name;
};

class EventAction : public G4UserEventAction
{
  public:
    EventAction(RunAction* runAction);
    ~EventAction() override = default;

    void BeginOfEventAction(const G4Event* event) override;
    void EndOfEventAction(const G4Event* event) override;

    void AddEdep(G4double edep) { fEdep += edep; }
    void AddLayerEdep(const G4String& name, G4double edep) { fLayerEdep[name] += edep; }
    void AddStep(const StepRecord& rec) { fSteps.push_back(rec); }

  private:
    RunAction* fRunAction = nullptr;
    G4double fEdep = 0.;
    std::map<G4String, G4double> fLayerEdep;
    std::vector<StepRecord> fSteps;
};

}  // namespace B1

#endif
