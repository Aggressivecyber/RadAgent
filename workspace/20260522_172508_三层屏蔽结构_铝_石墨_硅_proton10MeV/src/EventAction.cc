#include "EventAction.hh"
#include "RunAction.hh"
#include "G4Event.hh"
#include "G4PrimaryParticle.hh"
#include "G4PrimaryVertex.hh"
#include "G4ParticleDefinition.hh"
#include "G4SystemOfUnits.hh"
#include "G4TrajectoryContainer.hh"

namespace B1
{

EventAction::EventAction(RunAction* runAction)
  : fRunAction(runAction)
{}

void EventAction::BeginOfEventAction(const G4Event*)
{
  fEdep = 0.;
  fLayerEdep.clear();
  fSteps.clear();
}

void EventAction::EndOfEventAction(const G4Event* event)
{
  fRunAction->AddEdep(fEdep);
  for (const auto& [name, edep] : fLayerEdep) {
    fRunAction->AddLayerEdep(name, edep);
  }

  // 获取初始粒子信息
  G4String initialParticle = "unknown";
  G4double initialEnergy = 0.;
  if (event->GetNumberOfPrimaryVertex() > 0) {
    auto* vertex = event->GetPrimaryVertex(0);
    if (vertex->GetNumberOfParticle() > 0) {
      auto* primary = vertex->GetPrimary(0);
      initialParticle = primary->GetParticleDefinition()->GetParticleName();
      initialEnergy = primary->GetMomentum().mag() / MeV;
    }
  }

  // 最终动能
  G4double finalKinetic = 0.;
  if (!fSteps.empty()) {
    finalKinetic = fSteps.back().kinetic_energy;
  }

  // 次级粒子数
  G4int numSecondaries = 0;
  auto* trajectoryContainer = event->GetTrajectoryContainer();
  if (trajectoryContainer) {
    numSecondaries = static_cast<G4int>(trajectoryContainer->entries()) - 1;
    if (numSecondaries < 0) numSecondaries = 0;
  }

  // 写入逐事件 CSV
  auto& evtFile = fRunAction->GetEventFile();
  if (evtFile.is_open()) {
    evtFile << event->GetEventID() << ","
            << initialParticle << ","
            << initialEnergy << ","
            << fEdep / MeV << ","
            << fSteps.size() << ","
            << finalKinetic << ","
            << numSecondaries << "\n";
  }

  // 写入逐步 CSV
  auto& stpFile = fRunAction->GetStepFile();
  if (stpFile.is_open()) {
    G4int stepId = 0;
    for (const auto& step : fSteps) {
      stpFile << event->GetEventID() << ","
              << stepId++ << ","
              << step.particle_name << ","
              << step.kinetic_energy << ","
              << step.x << ","
              << step.y << ","
              << step.z << ","
              << step.volume_name << ","
              << step.edep << ","
              << step.step_length << ","
              << step.process_name << "\n";
    }
  }
}

}  // namespace B1
