#include "VoxelScorer.hh"
#include "G4Material.hh"
#include "G4SystemOfUnits.hh"
#include <cmath>
#include <iomanip>
#include <sstream>

VoxelScorer* VoxelScorer::fInstance = nullptr;

VoxelScorer* VoxelScorer::GetInstance() {
  if (!fInstance) {
    fInstance = new VoxelScorer();
  }
  return fInstance;
}

VoxelScorer::VoxelScorer()
  : fVoxelSize(0.),
    fTargetSizeX(0.), fTargetSizeY(0.), fTargetSizeZ(0.),
    fMinX(0.), fMinY(0.), fMinZ(0.),
    fNX(0), fNY(0), fNZ(0),
    fVoxelVolume(0.), fMassPerVoxel(0.), fDensity(0.)
{}

VoxelScorer::~VoxelScorer() {}

void VoxelScorer::Initialize(G4double voxelSize,
                             G4double targetSizeX,
                             G4double targetSizeY,
                             G4double targetSizeZ,
                             G4Material* mat) {
  fVoxelSize = voxelSize;
  fTargetSizeX = targetSizeX;
  fTargetSizeY = targetSizeY;
  fTargetSizeZ = targetSizeZ;

  fMinX = -targetSizeX / 2.0;
  fMinY = -targetSizeY / 2.0;
  fMinZ = -targetSizeZ / 2.0;

  fNX = std::floor(targetSizeX / voxelSize + 0.5);  // 20
  fNY = std::floor(targetSizeY / voxelSize + 0.5);  // 20
  fNZ = std::floor(targetSizeZ / voxelSize + 0.5);  // 6

  fEdep.assign(fNX * fNY * fNZ, 0.0);
  fDose.assign(fNX * fNY * fNZ, 0.0);

  // Voxel volume in cm^3 (1 um^3 = 1e-12 cm^3, actually 1 um = 1e-4 cm, so 1 um^3 = 1e-12 cm^3)
  G4double voxelVol_cm3 = (voxelSize / cm) * (voxelSize / cm) * (voxelSize / cm) * (cm*cm*cm);
  fVoxelVolume = voxelVol_cm3; // in cm^3

  // Density in g/cm^3
  fDensity = mat->GetDensity() / (g/cm3);  // GetDensity returns in g/cm^3 by default
  fMassPerVoxel = fDensity * fVoxelVolume;  // g
}

void VoxelScorer::Clear() {
  std::fill(fEdep.begin(), fEdep.end(), 0.0);
  std::fill(fDose.begin(), fDose.end(), 0.0);
}

void VoxelScorer::AddEdep(const G4ThreeVector& worldPos, G4double edep) {
  G4int ix, iy, iz;
  PositionToIndices(worldPos, ix, iy, iz);
  if (ix < 0 || ix >= fNX || iy < 0 || iy >= fNY || iz < 0 || iz >= fNZ) {
    return;  // outside target (should not happen if hit is in target)
  }
  G4int idx = iz * fNX * fNY + iy * fNX + ix;
  fEdep[idx] += edep;
}

void VoxelScorer::PositionToIndices(const G4ThreeVector& worldPos, G4int& ix, G4int& iy, G4int& iz) const {
  G4double x = worldPos.x();
  G4double y = worldPos.y();
  G4double z = worldPos.z();
  ix = std::floor((x - fMinX) / fVoxelSize);
  iy = std::floor((y - fMinY) / fVoxelSize);
  iz = std::floor((z - fMinZ) / fVoxelSize);
}

void VoxelScorer::WriteCSV(const G4String& outputDir) {
  // Compute dose after all events (total edep per voxel / mass per voxel)
  // Energy in MeV, convert to J: 1 MeV = 1.60217662e-13 J
  // Mass in g, convert to kg: 1 g = 1e-3 kg
  // Dose in Gy = (Edep_J) / (mass_kg)
  G4double conv = 1.60217662e-13 / (1e-3);  // (J/MeV) / (kg/g) = 1.60217662e-10 J*kg^{-1}*g*MeV^{-1}? Actually:
  // Dose = (edep_MeV) * 1.602e-13 J/MeV / (mass_g * 1e-3 kg/g) = edep_MeV * 1.602e-10 / mass_g
  // So we multiply edep by conv_factor / mass_g
  G4double convFactor = 1.60217662e-10;  // J/kg per MeV/g

  for (G4int i = 0; i < fNX * fNY * fNZ; ++i) {
    fDose[i] = fEdep[i] * convFactor / fMassPerVoxel;  // Gy
  }

  // Open output file
  G4String fileName = outputDir + "/scoring.csv";
  std::ofstream outFile(fileName, std::ios::out);
  if (!outFile.is_open()) {
    G4Exception("VoxelScorer::WriteCSV", "FileOpenFailed", FatalException, "Cannot open output file.");
    return;
  }

  // Write header
  outFile << "x_um,y_um,z_um,edep_MeV,dose_Gy\n";

  // Write voxel centers
  for (G4int iz = 0; iz < fNZ; ++iz) {
    G4double z_center = fMinZ + (iz + 0.5) * fVoxelSize;
    for (G4int iy = 0; iy < fNY; ++iy) {
      G4double y_center = fMinY + (iy + 0.5) * fVoxelSize;
      for (G4int ix = 0; ix < fNX; ++ix) {
        G4double x_center = fMinX + (ix + 0.5) * fVoxelSize;
        G4int idx = iz * fNX * fNY + iy * fNX + ix;
        outFile << x_center/um << ","
                << y_center/um << ","
                << z_center/um << ","
                << fEdep[idx] << ","
                << fDose[idx] << "\n";
      }
    }
  }
  outFile.close();
  G4cout << "Scoring data written to " << fileName << G4endl;
}
