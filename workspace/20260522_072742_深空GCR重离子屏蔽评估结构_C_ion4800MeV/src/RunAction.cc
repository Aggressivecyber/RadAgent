#include "RunAction.hh"

#include "G4AccumulableManager.hh"
#include "G4Run.hh"
#include "G4RunManager.hh"
#include "G4SystemOfUnits.hh"
#include "G4UnitsTable.hh"
#include "G4Threading.hh"
#include "G4AutoDelete.hh"

#include <cmath>
#include <sstream>
#include <filesystem>

namespace B1
{

RunAction::RunAction()
{
  G4AccumulableManager* mgr = G4AccumulableManager::Instance();
  mgr->Register(fEdep);
  mgr->Register(fEdep2);
  mgr->Register(fLayerEdep);
}

RunAction::~RunAction()
{
  if (fEventFile.is_open()) fEventFile.close();
  if (fStepFile.is_open()) fStepFile.close();
}

void RunAction::BeginOfRunAction(const G4Run* run)
{
  G4RunManager::GetRunManager()->SetRandomNumberStore(false);
  G4AccumulableManager::Instance()->Reset();

  // 每个线程打开自己的 CSV 文件
  G4int threadId = G4Threading::G4GetThreadId();
  std::ostringstream evtPath, stpPath;
  evtPath << "radagent_events_t" << threadId << ".csv";
  stpPath << "radagent_steps_t" << threadId << ".csv";

  fEventFile.open(evtPath.str());
  fStepFile.open(stpPath.str());

  // 写 CSV header
  if (fEventFile.is_open()) {
    fEventFile << "event_id,initial_particle,initial_energy_MeV,total_edep_MeV,"
               << "num_steps,final_kinetic_MeV,num_secondaries\n";
  }
  if (fStepFile.is_open()) {
    fStepFile << "event_id,step_id,particle,kinetic_MeV,x_cm,y_cm,z_cm,"
              << "volume,edep_MeV,step_length_mm,process\n";
  }
}

void RunAction::AddEdep(G4double edep)
{
  fEdep += edep;
  fEdep2 += edep * edep;
}

void RunAction::AddLayerEdep(const G4String& layerName, G4double edep)
{
  fLayerEdep[layerName] += edep;
}

void RunAction::EndOfRunAction(const G4Run* run)
{
  // 关闭文件（确保 flush）
  if (fEventFile.is_open()) { fEventFile.flush(); fEventFile.close(); }
  if (fStepFile.is_open()) { fStepFile.flush(); fStepFile.close(); }

  G4int nofEvents = run->GetNumberOfEvent();
  if (nofEvents == 0) return;

  G4AccumulableManager::Instance()->Merge();

  if (!G4Threading::IsMasterThread()) return;

  // 合并所有线程的 CSV 文件到最终输出
  // 使用 istreambuf_iterator 显式读取，避免 rdbuf() 在 getline 后位置异常
  {
    std::ofstream out("radagent_events.csv");
    out << "event_id,initial_particle,initial_energy_MeV,total_edep_MeV,"
        << "num_steps,final_kinetic_MeV,num_secondaries\n";
    for (G4int t = -1; t < 256; ++t) {
      std::ostringstream path;
      path << "radagent_events_t" << t << ".csv";
      std::ifstream in(path.str());
      if (in.good()) {
        std::string header;
        std::getline(in, header);
        out << std::string((std::istreambuf_iterator<char>(in)),
                           std::istreambuf_iterator<char>());
      }
      std::filesystem::remove(path.str());
    }
    out.flush();
    out.close();
  }

  {
    std::ofstream out("radagent_steps.csv");
    out << "event_id,step_id,particle,kinetic_MeV,x_cm,y_cm,z_cm,"
        << "volume,edep_MeV,step_length_mm,process\n";
    for (G4int t = -1; t < 256; ++t) {
      std::ostringstream path;
      path << "radagent_steps_t" << t << ".csv";
      std::ifstream in(path.str());
      if (in.good()) {
        std::string header;
        std::getline(in, header);
        out << std::string((std::istreambuf_iterator<char>(in)),
                           std::istreambuf_iterator<char>());
      }
      std::filesystem::remove(path.str());
    }
    out.flush();
    out.close();
  }

  // 输出汇总信息
  G4double edep = fEdep.GetValue();
  G4double edep2 = fEdep2.GetValue();

  G4double rms = edep2 - edep * edep / nofEvents;
  if (rms > 0.) rms = std::sqrt(rms / nofEvents);
  else rms = 0.;

  const G4double mass = 4.0 * kg;
  G4double dose = edep / mass;
  G4double rmsDose = rms / mass;

  G4cout << "\n====== 仿真结果 ======" << G4endl;
  G4cout << "总事件数: " << nofEvents << G4endl;
  G4cout << "\n总能量沉积: " << G4BestUnit(edep, "Energy")
         << " rms = " << G4BestUnit(rms, "Energy") << G4endl;
  G4cout << "敏感体积剂量: " << G4BestUnit(dose, "Dose")
         << " rms = " << G4BestUnit(rmsDose, "Dose") << G4endl;

  const auto& layerMap = fLayerEdep.GetMap();
  if (!layerMap.empty()) {
    G4cout << "\n--- 逐层能量沉积 ---" << G4endl;
    for (const auto& [name, layerEdep] : layerMap) {
      G4cout << "  " << name << ": " << G4BestUnit(layerEdep, "Energy") << G4endl;
    }
  }
  G4cout << "\n输出文件: radagent_events.csv, radagent_steps.csv" << G4endl;
  G4cout << "======================\n" << G4endl;
}

}  // namespace B1
