#include "OutputManager.hh"
#include "G4SystemOfUnits.hh"
#include "G4UnitsTable.hh"
#include "G4RunManager.hh"
#include <iostream>
#include <iomanip>
#include <cmath>
#include <filesystem>
#include <ctime>

namespace {
constexpr G4double kGridOriginXmm = -100.0;
constexpr G4double kGridOriginYmm = -100.0;
constexpr G4double kGridOriginZmm = -2.5;
constexpr int kCsvPrecision = 6;
constexpr int kTimestampBufferSize = 64;
constexpr const char* kGeant4VersionString = "11.3";
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

OutputManager* OutputManager::Instance()
{
  static OutputManager instance;
  return &instance;
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

OutputManager::OutputManager()
  : fOutputDir("output"),
    fGrid(kNxBins * kNyBins * kNzBins),
    fCurrentEdep(0.0),
    fCurrentDose(0.0),
    fRunStartTime(0.0)
{
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

OutputManager::~OutputManager() = default;

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void OutputManager::SetOutputDir(const G4String& dir)
{
  fOutputDir = dir;
}

G4String OutputManager::GetOutputDir() const
{
  return fOutputDir;
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

G4String OutputManager::ResolveOutputDir() const
{
  const char* envDir = std::getenv("G4_OUTPUT_DIR");
  if (envDir != nullptr) {
    return G4String(envDir);
  }
  return fOutputDir;
}

void OutputManager::EnsureOutputDir() const
{
  G4String dir = ResolveOutputDir();
  std::filesystem::create_directories(dir.c_str());
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

G4int OutputManager::BinIndex(G4int ix, G4int iy, G4int iz) const
{
  return ix + kNxBins * (iy + kNyBins * iz);
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void OutputManager::BeginOfRun()
{
  fRunStartTime = 0.0;
  fEventRecords.clear();
  std::fill(fGrid.begin(), fGrid.end(), GridBin{0.0, 0.0});
  
  EnsureOutputDir();
}

void OutputManager::EndOfRun()
{
  G4int totalEvents = static_cast<G4int>(fEventRecords.size());
  
  WriteEventTable();
  WriteEdep3D();
  WriteDose3D();
  WriteSummary(totalEvents);
  WriteProvenance();
  
  G4cout << "==== OutputManager: Artifacts written to " << ResolveOutputDir() << " ====" << G4endl;
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void OutputManager::BeginOfEvent()
{
  fCurrentEdep = 0.0;
  fCurrentDose = 0.0;
}

void OutputManager::EndOfEvent(G4int eventID)
{
  EventRecord rec;
  rec.eventID = eventID;
  rec.edepMeV = fCurrentEdep;
  rec.doseGy = fCurrentDose;
  fEventRecords.push_back(rec);
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void OutputManager::AddEventScoring(G4double edepMeV, G4double doseGy)
{
  fCurrentEdep += edepMeV;
  fCurrentDose += doseGy;
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void OutputManager::Record3DHit(const G4ThreeVector& pos, G4double edepMeV)
{
  // Convert position from mm to bin indices
  // Silicon detector: x[-10,10] cm = [-100,100] mm, y[-10,10] cm = [-100,100] mm, z[-0.25,0.25] cm = [-2.5,2.5] mm
  G4double x_mm = pos.x();
  G4double y_mm = pos.y();
  G4double z_mm = pos.z();
  
  G4int ix = static_cast<G4int>(std::floor((x_mm - kGridOriginXmm) / kBinSizeXY));
  G4int iy = static_cast<G4int>(std::floor((y_mm - kGridOriginYmm) / kBinSizeXY));
  G4int iz = static_cast<G4int>(std::floor((z_mm - kGridOriginZmm) / kBinSizeZ));
  
  // Check bounds
  if (ix < 0 || ix >= kNxBins || iy < 0 || iy >= kNyBins || iz < 0 || iz >= kNzBins) {
    return; // Out of bounds
  }
  
  G4int idx = BinIndex(ix, iy, iz);
  
  // Accumulate energy deposition
  fGrid[idx].edepMeV += edepMeV;
  
  // Calculate dose for this voxel: dose [Gy] = edep [J] / mass [kg]
  G4double edep_J = edepMeV * kMeVtoJoule;
  G4double dose_Gy = edep_J / kVoxelMassKg;
  fGrid[idx].doseGy += dose_Gy;
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void OutputManager::WriteEventTable()
{
  G4String dir = ResolveOutputDir();
  G4String path = dir + "/event_table.csv";
  
  std::ofstream ofs(path.c_str());
  if (!ofs.is_open()) {
    G4cerr << "OutputManager: Could not open " << path << G4endl;
    return;
  }
  
  ofs << "EventID,edep_MeV,dose_Gy" << std::endl;
  for (const auto& rec : fEventRecords) {
    ofs << rec.eventID << ","
        << std::scientific << std::setprecision(kCsvPrecision) << rec.edepMeV << ","
        << std::scientific << std::setprecision(kCsvPrecision) << rec.doseGy
        << std::endl;
  }
  ofs.close();
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void OutputManager::WriteEdep3D()
{
  G4String dir = ResolveOutputDir();
  G4String path = dir + "/edep_3d.csv";
  
  std::ofstream ofs(path.c_str());
  if (!ofs.is_open()) {
    G4cerr << "OutputManager: Could not open " << path << G4endl;
    return;
  }
  
  ofs << "x_mm,y_mm,z_mm,edep_MeV" << std::endl;
  
  G4int count = 0;
  for (G4int iz = 0; iz < kNzBins; ++iz) {
    for (G4int iy = 0; iy < kNyBins; ++iy) {
      for (G4int ix = 0; ix < kNxBins; ++ix) {
        G4int idx = BinIndex(ix, iy, iz);
        G4double edep = fGrid[idx].edepMeV;
        if (edep > 0.0) {
          G4double x = kGridOriginXmm + (ix + 0.5) * kBinSizeXY;
          G4double y = kGridOriginYmm + (iy + 0.5) * kBinSizeXY;
          G4double z = kGridOriginZmm + (iz + 0.5) * kBinSizeZ;
          ofs << std::fixed << std::setprecision(2) << x << ","
              << y << "," << z << ","
              << std::scientific << std::setprecision(kCsvPrecision) << edep
              << std::endl;
          count++;
        }
      }
    }
  }
  
  // If no hits, write at least one entry at center with zero
  if (count == 0) {
    ofs << "0.00,0.00,0.00,0.000000e+00" << std::endl;
  }
  
  ofs.close();
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void OutputManager::WriteDose3D()
{
  G4String dir = ResolveOutputDir();
  G4String path = dir + "/dose_3d.csv";
  
  std::ofstream ofs(path.c_str());
  if (!ofs.is_open()) {
    G4cerr << "OutputManager: Could not open " << path << G4endl;
    return;
  }
  
  ofs << "x_mm,y_mm,z_mm,dose_Gy" << std::endl;
  
  G4int count = 0;
  for (G4int iz = 0; iz < kNzBins; ++iz) {
    for (G4int iy = 0; iy < kNyBins; ++iy) {
      for (G4int ix = 0; ix < kNxBins; ++ix) {
        G4int idx = BinIndex(ix, iy, iz);
        G4double dose = fGrid[idx].doseGy;
        if (dose > 0.0) {
          G4double x = kGridOriginXmm + (ix + 0.5) * kBinSizeXY;
          G4double y = kGridOriginYmm + (iy + 0.5) * kBinSizeXY;
          G4double z = kGridOriginZmm + (iz + 0.5) * kBinSizeZ;
          ofs << std::fixed << std::setprecision(2) << x << ","
              << y << "," << z << ","
              << std::scientific << std::setprecision(kCsvPrecision) << dose
              << std::endl;
          count++;
        }
      }
    }
  }
  
  // If no hits, write at least one entry at center with zero
  if (count == 0) {
    ofs << "0.00,0.00,0.00,0.000000e+00" << std::endl;
  }
  
  ofs.close();
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void OutputManager::WriteSummary(G4int totalEvents)
{
  G4String dir = ResolveOutputDir();
  G4String path = dir + "/g4_summary.json";
  
  std::ofstream ofs(path.c_str());
  if (!ofs.is_open()) {
    G4cerr << "OutputManager: Could not open " << path << G4endl;
    return;
  }
  
  G4double totalEdep = 0.0;
  G4double totalDose = 0.0;
  for (const auto& rec : fEventRecords) {
    totalEdep += rec.edepMeV;
    totalDose += rec.doseGy;
  }
  
  ofs << "{" << std::endl;
  ofs << "  \"total_events\": " << totalEvents << "," << std::endl;
  ofs << "  \"events_requested\": " << totalEvents << "," << std::endl;
  ofs << "  \"total_edep_MeV\": " << std::scientific << std::setprecision(kCsvPrecision) << totalEdep << "," << std::endl;
  ofs << "  \"total_dose_Gy\": " << std::scientific << std::setprecision(kCsvPrecision) << totalDose << "," << std::endl;
  ofs << "  \"avg_edep_MeV_per_event\": " << (totalEvents > 0 ? totalEdep / totalEvents : 0.0) << "," << std::endl;
  ofs << "  \"avg_dose_Gy_per_event\": " << (totalEvents > 0 ? totalDose / totalEvents : 0.0) << std::endl;
  ofs << "}" << std::endl;
  
  ofs.close();
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void OutputManager::WriteProvenance()
{
  G4String dir = ResolveOutputDir();
  G4String path = dir + "/provenance.json";
  
  std::ofstream ofs(path.c_str());
  if (!ofs.is_open()) {
    G4cerr << "OutputManager: Could not open " << path << G4endl;
    return;
  }
  
  // Get current time
  auto now = std::time(nullptr);
  auto* tm = std::localtime(&now);
  char timeStr[kTimestampBufferSize];
  std::strftime(timeStr, sizeof(timeStr), "%Y-%m-%dT%H:%M:%S", tm);
  
  ofs << "{" << std::endl;
  ofs << "  \"tool\": \"Geant4\"," << std::endl;
  ofs << "  \"version\": \"" << kGeant4VersionString << "\"," << std::endl;
  ofs << "  \"timestamp\": \"" << timeStr << "\"," << std::endl;
  ofs << "  \"physics_list\": \"FTFP_BERT\"," << std::endl;
  ofs << "  \"detector\": \"RadAgent Silicon Detector\"," << std::endl;
  ofs << "  \"scoring\": \"energy_dose_3d\"" << std::endl;
  ofs << "}" << std::endl;
  
  ofs.close();
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......