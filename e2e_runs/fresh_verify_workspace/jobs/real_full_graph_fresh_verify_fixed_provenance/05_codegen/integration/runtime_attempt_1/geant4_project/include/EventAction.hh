#ifndef EVENT_ACTION_HH
#define EVENT_ACTION_HH

#include "G4UserEventAction.hh"

class G4Event;

class EventAction : public G4UserEventAction
{
public:
  EventAction();
  ~EventAction() override;

  void BeginOfEventAction(const G4Event* event) override;
  void EndOfEventAction(const G4Event* event) override;
};

#endif
