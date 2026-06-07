# Model Review — Complex Silicon Pixel Detector Module

**Job ID:** `complex_dev`
**Validation Status:** PARTIAL (dev mode)
**Date:** 2026-06-07

> NOT VERIFIED — 8 gates skipped in dev mode. Cannot claim VERIFIED without acceptance tests.

---

## 1. Components (9)

| # | Component ID | Type | Geometry | Material | Mother Volume | Roles |
|---|-------------|------|----------|----------|--------------|-------|
| 1 | `world` | world | box 5000×5000×5000 mm | G4_AIR | — | — |
| 2 | `housing` | shielding | box 100×100×50 mm | G4_Al | world | shielding, mechanical_support |
| 3 | `pcb` | substrate | box 80×80×5 mm | FR4 | housing | mechanical_support |
| 4 | `sensor_stack` | assembly | box 50×50×20 mm | G4_AIR | pcb | assembly_container |
| 5 | `top_electrode` | electrode | box 50×50×1 mm | G4_Al | sensor_stack | electrode |
| 6 | `oxide_layer` | layer | box 50×50×0.001 mm | SiO2 | sensor_stack | dielectric |
| 7 | `silicon_bulk` | volume | box 50×50×10 mm | G4_Si | sensor_stack | active_material |
| 8 | `sensitive_region` | volume | box 48×48×5 mm | G4_Si | silicon_bulk | edep_region, active_detector |
| 9 | `bottom_electrode` | electrode | box 50×50×1 mm | G4_Al | sensor_stack | electrode |

**Hierarchy:** world → housing → pcb → sensor_stack → {top_electrode, oxide_layer, silicon_bulk → sensitive_region, bottom_electrode}

---

## 2. Materials (5)

| Material ID | Classification | Key Property | Source |
|------------|---------------|-------------|--------|
| G4_AIR | NIST | ρ = 0.001214 g/cm³ | NIST standard |
| G4_Al | NIST | ρ = 2.699 g/cm³ | NIST standard |
| FR4 | custom | ρ = 1.85 g/cm³, 8-element composition | Material database |
| G4_Si | NIST | ρ = 2.329 g/cm³ | NIST standard |
| SiO2 | custom | ρ = 2.2 g/cm³, Si:O = 1:2 | Material database |

Custom materials (FR4, SiO2) have explicit element compositions with source evidence.

---

## 3. Source Specification

| Field | Value |
|-------|-------|
| Particle | proton |
| Energy | 10 MeV, mono |
| Position | [0, 0, 4900000] um |
| Direction | [0, 0, -1] (vertical incidence) |
| Generator | GPS |
| Events | 200,000 |

---

## 4. Scoring (4)

| Scoring ID | Type | Region | Quantities | Output |
|-----------|------|--------|------------|--------|
| sensitive_edep | region | sensitive_region | event_id, edep_MeV, n_entries | CSV |
| oxide_dose | region | oxide_layer | event_id, dose_Gy, edep_MeV | CSV |
| bulk_dose_3d | mesh | silicon_bulk | voxel_id, x_mm, y_mm, z_mm, dose_Gy, edep_MeV | CSV |
| event_table | region | sensitive_region | event_id, edep_MeV, x_mm, y_mm, z_mm | CSV |

---

## 5. Physics

- **Physics List:** QGSP_BIC_HP
- **Reasoning:** Standard EM + hadronic for proton simulation with high-precision neutron transport

---

## 6. No-Simplification Result (G4-B)

- **allow_simplification:** false
- **requires_user_approval:** true
- **approved_simplifications:** [] (empty)
- **All 8 non-world components preserved individually:** housing ✓, pcb ✓, sensor_stack ✓, top_electrode ✓, oxide_layer ✓, silicon_bulk ✓, sensitive_region ✓, bottom_electrode ✓
- **missing_components:** [] (none)
- **unapproved_simplifications:** [] (none)
- **Layer merge detected:** No

---

## 7. Geometry Interface Result (G4-C)

8 mother-daughter interfaces validated:

| Interface | Parent | Child | Valid |
|-----------|--------|-------|-------|
| world_housing | world | housing | ✓ |
| housing_pcb | housing | pcb | ✓ |
| pcb_sensor_stack | pcb | sensor_stack | ✓ |
| sensor_stack_top_electrode | sensor_stack | top_electrode | ✓ |
| sensor_stack_oxide | sensor_stack | oxide_layer | ✓ |
| sensor_stack_si_bulk | sensor_stack | silicon_bulk | ✓ |
| si_bulk_sensitive | silicon_bulk | sensitive_region | ✓ |
| sensor_stack_bottom_electrode | sensor_stack | bottom_electrode | ✓ |

All mother_volume references resolvable. No orphan references.

---

## 8. Evidence Traceability (G4-E)

All parameters have traceable source_evidence:
- Components: user_specification, detector_design, geant4_convention
- Custom materials: material_database
- Physics: geant4_physics_guide
- Scoring: user_specification

---

## 9. Skipped Gates (8)

| Gate ID | Name | Reason |
|---------|------|--------|
| 0 | Context Sufficiency | Dev mode, no RAG/Web |
| 3 | Patch Format | Dev mode, no patch |
| 4 | File Permission | Dev mode, no files written |
| 6 | Build/Parse | No Geant4 build environment |
| 7 | Unit Tests | Acceptance-only gate |
| 9 | Smoke Simulation | Acceptance-only gate |
| 10 | Benchmark Regression | No baseline data |
| 11 | Physics Sanity | No simulation output |

---

## 10. Known Limitations

1. Dev mode (dev_no_geant4_env): 8 gates skipped — require Geant4 runtime
2. No actual simulation run — scoring outputs are planned, not populated with data
3. C++ code is generated but not compiled or tested
4. Smoke test (Gate 9) skipped — acceptance-only gate

---

## 11. Verification Status

**PARTIAL** — Cannot claim VERIFIED. All static/structural gates pass (1, 2, 5, 8, G4-A through G4-G), but runtime gates require Geant4 environment for compilation, execution, and output validation.
