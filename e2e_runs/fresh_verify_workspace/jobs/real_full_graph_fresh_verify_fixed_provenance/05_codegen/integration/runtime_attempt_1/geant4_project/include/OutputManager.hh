#ifndef OUTPUT_MANAGER_HH
#define OUTPUT_MANAGER_HH

#include "globals.hh"
#include "G4ThreeVector.hh"
#include <fstream>
#include <string>
#include <vector>
#include <map>

class OutputManager
{
public:
  static OutputManager* Instance();
  OutputManager();
  ~OutputManager();

  // Directory control
  void SetOutputDir(const G4String& dir);
  G4String GetOutputDir() const;

  // Run lifecycle
  void BeginOfRun();
  void EndOfRun();

  // Event lifecycle
  void BeginOfEvent();
  void EndOfEvent(G4int eventID);

  // Per-event scoring from ScoringManager
  void AddEventScoring(G4double edepMeV, G4double doseGy);

  // 3D hit recording
  void Record3DHit(const G4ThreeVector& pos, G4double edepMeV);

private:
  // Output directory
  G4String ResolveOutputDir() const;
  void EnsureOutputDir() const;

  // Artifact writers
  void WriteEventTable();
  void WriteEdep3D();
  void WriteDose3D();
  void WriteSummary(G4int totalEvents);
  void WriteProvenance();

  struct EventRecord
  {
    G4int eventID = 0;
    G4double edepMeV = 0.0;
    G4double doseGy = 0.0;
  };

  struct GridBin
  {
    G4double edepMeV = 0.0;
    G4double doseGy = 0.0;
  };

  // 3D grid for silicon detector: x[-10,10], y[-10,10], z[-0.25,0.25]
  static constexpr G4int kNxBins = 20;
  static constexpr G4int kNyBins = 20;
  static constexpr G4int kNzBins = 1;
  static constexpr G4double kBinSizeXY = 2.0; // mm
  static constexpr G4double kBinSizeZ  = 0.5; // mm
  static constexpr G4double kVoxelVolumeMm3 = kBinSizeXY * kBinSizeXY * kBinSizeZ; // 2.0 mm3
  static constexpr G4double kSiDensityKgPerMm3 = 2.33e-6; // G4_Si ~2.33 g/cm3 = 2.33e-6 kg/mm3
  static constexpr G4double kVoxelMassKg = kVoxelVolumeMm3 * kSiDensityKgPerMm3;
  static constexpr G4double kMeVtoJoule = 1.602176634e-13; // 1 MeV = 1.602e-13 J

  G4int BinIndex(G4int ix, G4int iy, G4int iz) const;

  G4String fOutputDir;

  // Accumulated 3D grid across entire run
  std::vector<GridBin> fGrid;

  // Per-event records
  std::vector<EventRecord> fEventRecords;

  // Current event accumulators
  G4double fCurrentEdep = 0.0;
  G4double fCurrentDose = 0.0;

  // Timing
  G4double fRunStartTime = 0.0;
};

#endif