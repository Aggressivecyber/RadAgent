#ifndef STEPPING_ACTION_HH
#define STEPPING_ACTION_HH

#include "G4UserSteppingAction.hh"
#include "G4LogicalVolume.hh"

class G4Step;

class SteppingAction : public G4UserSteppingAction
{
public:
  SteppingAction();
  ~SteppingAction() override;

  void UserSteppingAction(const G4Step* step) override;

  void SetScoringVolume(G4LogicalVolume* lv);

private:
  G4LogicalVolume* fScoringVolume = nullptr;
};

#endif
