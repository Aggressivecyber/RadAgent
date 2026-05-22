#ifndef B1SteppingAction_h
#define B1SteppingAction_h 1

#include "G4UserSteppingAction.hh"
#include <vector>

class G4LogicalVolume;
class G4Step;

namespace B1
{

class EventAction;

class SteppingAction : public G4UserSteppingAction
{
  public:
    SteppingAction(EventAction* eventAction);
    ~SteppingAction() override = default;

    void UserSteppingAction(const G4Step*) override;

  private:
    EventAction* fEventAction = nullptr;
    std::vector<G4LogicalVolume*> fScoringVolumes;
};

}  // namespace B1

#endif
