# Model Review Report - Radiation-Hard Silicon Pixel Detector

## Artifact Info
- **Kind**: g4_complex_model
- **Run Type**: test
- **Is Stub**: false
- **Job ID**: rad_detector_complex
- **Validation Status**: passed
- **Validation Scope**: fixture_model_review

## Model Summary

### Components (9)
| ID | Type | Material | Parent | Roles |
|----|------|----------|--------|-------|
| world | world | G4_AIR | root | root |
| housing | volume | G4_Al | world | housing, shielding |
| pcb | volume | FR4 | housing | mechanical_support |
| sensor_stack | assembly | G4_AIR | pcb | assembly |
| top_electrode | volume | G4_Al | sensor_stack | electrode |
| oxide_layer | volume | SiO2 | sensor_stack | oxide, dose_critical |
| silicon_bulk | volume | G4_Si | sensor_stack | substrate |
| sensitive_region | volume | G4_Si | silicon_bulk | edep_region, sensitive_detector |
| bottom_electrode | volume | G4_Al | sensor_stack | electrode |

### Materials (5)
| ID | Type | Density (g/cm³) |
|----|------|-----------------|
| G4_AIR | NIST | 0.001214 |
| G4_Al | NIST | 2.699 |
| FR4 | custom | 1.850 |
| G4_Si | NIST | 2.329 |
| SiO2 | custom | 2.200 |

### Source
- **Particle**: proton, 10 MeV, mono-energetic
- **Position**: (0, 0, 1500) mm
- **Direction**: (0, 0, -1), vertical incidence

### Scoring (4)
1. **sensitive_edep**: region scoring on sensitive_region, edep_MeV and n_entries
2. **oxide_dose**: region scoring on oxide_layer, dose_Gy and edep_MeV
3. **bulk_dose_3d**: mesh scoring on silicon_bulk, dose_Gy and edep_MeV (5 mm voxels)
4. **event_table**: region scoring on sensitive_region, event_id, edep, position

### Physics
- **List**: QGSP_BIC_HP
- **Reasoning**: Binary cascade for low-energy proton, HP neutron, standard EM

## Simplification Check
- **Policy**: allow_simplification = false
- **All complex components preserved**: yes
- **No merged layers**: yes
- **No missing components**: yes

## Gate Summary
- Total: 20 gates
- Passed: 10
- Skipped: 10 (non-critical fixture-only gates)
- Failed: 0
- Warnings: 1
- Skipped Gates: Patch Format, File Permission, Static Check, Build/Parse, Unit Test, Data Contract, Smoke Simulation, Benchmark Regression, Physics Sanity, G4-G No Magic Number

## Known Limitations
1. Fixture artifact, no actual Geant4 simulation executed
2. Oxide layer 1 μm needs step limit control in production
3. 3D dose map mesh resolution limited by voxel size
4. OutputManager generates planned outputs, not actual data
5. Runtime job gates are skipped because this artifact stores review inputs only

## Human Confirmation
- **Status**: approved
- **Remaining Unconfirmed Fields**: 0

## Nesting Hierarchy
```
world
└── housing (Al)
    └── pcb (FR4)
        └── sensor_stack (air gap)
            ├── top_electrode (Al, 0.5 mm)
            ├── oxide_layer (SiO2, 1 μm)
            ├── silicon_bulk (Si, 30 mm)
            │   └── sensitive_region (Si, 25 mm, scored)
            └── bottom_electrode (Al, 0.5 mm)
```
