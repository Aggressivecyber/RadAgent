# Simulation Report: job_20260606_203227_e2296c

**Generated:** 2026-06-06T20:33:46.234640

## 1. User Request

模拟 10 MeV 质子垂直入射 300 微米硅片，输出能量沉积和剂量分布

## 2. Task Specification

```json
{
  "simulation_scope": [
    "geant4"
  ],
  "particle": {
    "type": "proton",
    "energy_MeV": 10.0,
    "direction": [
      0,
      0,
      1
    ],
    "events": 1000
  },
  "target": {
    "material": "Si",
    "size_um": [
      1000.0,
      1000.0,
      300.0
    ],
    "geometry_type": "box"
  },
  "outputs": [
    "energy_deposition",
    "dose_distribution"
  ],
  "metadata": {
    "source": "heuristic_parser"
  }
}
```

## 3. RAG Sources Used

- Routes: g4rag
- Sufficiency Score: 0.76
- Decision: allow_with_warning

## 4. Code Generation

- Patch ID: 438b45c9-a671-4f8e-8aa2-243fc3855902
- Description: A minimal Geant4 simulation with a silicon target (1000x1000x300 um) irradiated by 10 MeV protons along +z axis. Energy deposition and dose are scored in a 3D voxel grid (50 um resolution) and written to a single CSV file. The FTFP_BERT physics list is used. The code is designed for single-thread execution.
- Files Generated: 12
- Risk Level: low

## 5. Gate Results

- Gate 0: RAG Sufficiency -- PASS RAG score: 0.76
- Gate 1: Task Spec Schema -- PASS Valid
- Gate 2: Simulation IR Schema -- PASS Valid
- Gate 3: Patch Format -- PASS Valid
- Gate 4: File Permission -- PASS OK (green zone): simulation_workspace/jobs/job_20260606_203227_e2296c/05_geant4/CMakeLists.txt; OK (green zone): simulation_workspace/jobs/job_20260606_203227_e2296c/05_geant4/geant4_sim.cc; OK (green zone): simulation_workspace/jobs/job_20260606_203227_e2296c/05_geant4/DetectorConstruction.hh; OK (green zone): simulation_workspace/jobs/job_20260606_203227_e2296c/05_geant4/DetectorConstruction.cc; OK (green zone): simulation_workspace/jobs/job_20260606_203227_e2296c/05_geant4/PrimaryGeneratorAction.hh; OK (green zone): simulation_workspace/jobs/job_20260606_203227_e2296c/05_geant4/PrimaryGeneratorAction.cc; OK (green zone): simulation_workspace/jobs/job_20260606_203227_e2296c/05_geant4/VoxelScorer.hh; OK (green zone): simulation_workspace/jobs/job_20260606_203227_e2296c/05_geant4/VoxelScorer.cc; OK (green zone): simulation_workspace/jobs/job_20260606_203227_e2296c/05_geant4/SensitiveDetector.hh; OK (green zone): simulation_workspace/jobs/job_20260606_203227_e2296c/05_geant4/SensitiveDetector.cc; OK (green zone): simulation_workspace/jobs/job_20260606_203227_e2296c/05_geant4/RunAction.hh; OK (green zone): simulation_workspace/jobs/job_20260606_203227_e2296c/05_geant4/RunAction.cc
- Gate 5: Static Check -- FAIL No .cc files in src/; No .hh files in include/; Missing required class: DetectorConstruction; Missing required class: PhysicsList; Missing required class: PrimaryGeneratorAction; Missing required class: SteppingAction
- Gate 6: Build/Parse -- FAIL Build failed
- Gate 7: Unit Test -- PASS MVP-1: Auto-pass (will be implemented in later MVPs)
- Gate 8: Data Contract -- PASS MVP-1: Auto-pass (will be implemented in later MVPs)
- Gate 9: Smoke Simulation -- PASS MVP-1: Auto-pass (will be implemented in later MVPs)
- Gate 10: Benchmark Regression -- PASS MVP-1: Auto-pass (will be implemented in later MVPs)
- Gate 11: Physics Sanity -- PASS MVP-1: Auto-pass (will be implemented in later MVPs)

## 6. Simulation Results

No simulation results available.

## 7. Data Contract Validation


## 8. Failure Report

- Type: build_error
- Gate: Static Check (ID: 5)
- Message: No .cc files in src/; No .hh files in include/; Missing required class: DetectorConstruction; Missing required class: PhysicsList; Missing required class: PrimaryGeneratorAction; Missing required class: SteppingAction
- Retries: 5

## 9. Known Issues and Next Steps

- Some gates failed; review failure report above