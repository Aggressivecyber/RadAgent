#ifndef VoxelScorer_h
#define VoxelScorer_h 1

#include "globals.hh"
#include "G4ThreeVector.hh"
#include <vector>
#include <fstream>

class G4Material;

class VoxelScorer {
public:
  static VoxelScorer* GetInstance();

  void Initialize(G4double voxelSize,
                  G4double targetSizeX,
                  G4double targetSizeY,
                  G4double targetSizeZ,
                  G4Material* mat);
  void Clear();

  // Add energy deposition at a given world position inside target
  void AddEdep(const G4ThreeVector& worldPos, G4double edep);

  // Write scoring data to CSV file
  void WriteCSV(const G4String& outputDir);

private:
  VoxelScorer();
  ~VoxelScorer();
  VoxelScorer(const VoxelScorer&) = delete;
  VoxelScorer& operator=(const VoxelScorer&) = delete;

  // Convert world position to voxel indices
  void PositionToIndices(const G4ThreeVector& worldPos, G4int& ix, G4int& iy, G4int& iz) const;

  static VoxelScorer* fInstance;

  G4double fVoxelSize;
  G4double fTargetSizeX, fTargetSizeY, fTargetSizeZ;
  G4double fMinX, fMinY, fMinZ;  // target min corner
  G4int fNX, fNY, fNZ;  // number of voxels per dimension

  G4double fVoxelVolume;  // cm^3
  G4double fMassPerVoxel; // g
  G4double fDensity;      // g/cm^3

  std::vector<G4double> fEdep;   // in MeV
  std::vector<G4double> fDose;   // in Gy
};

#endif
