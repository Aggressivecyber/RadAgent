# G4 Model Review: mir_job_5574e228__20260616_070817
- **Job ID**: job_5574e228__20260616_070817
- **Mode**: realistic
- **Target**: Proton depth-dose benchmark through layered materials

## ✅ Validation Status: PASSED

## Geometry Components
| ID | Type | Material | Parent | Sensitive |
|----|------|----------|--------|-----------|
| world_001 | box | G4_Galactic | — |  |
| layer_water_001 | box | G4_WATER | world_001 | ✓ |
| layer_aluminum_001 | box | G4_Al | world_001 | ✓ |
| layer_silicon_001 | box | G4_Si | world_001 | ✓ |

## Materials
| ID | Name | Type | Density (g/cm³) |
|----|------|------|-----------------|
| G4_Al | G4_Al (NIST) | nist | 2.699 |
| G4_Galactic | G4_Galactic (NIST) | nist | 1e-25 |
| G4_Si | G4_Si (NIST) | nist | 2.33 |
| G4_WATER | G4_WATER (NIST) | nist | 1.0 |

## Particle Source
- **Particle**: proton
- **Energy**: 150.0 MeV (mono)
- **Events**: 1000
- **Position**: [0.0, 0.0, -400500.0] → direction [0.0, 0.0, 1.0]

## Physics
- **List**: FTFP_BERT
- **Reasoning**: FTFP_BERT is recommended for proton therapy simulations up to 10 GeV, providing good accuracy for electromagnetic and hadronic interactions in the requested energy range.

## Sensitive Detectors
- **LayerWater001SdSensitiveDetector**: linked to ['layer_water_001'], collection=layer_water_001_Hits
- **LayerAluminum001SdSensitiveDetector**: linked to ['layer_aluminum_001'], collection=layer_aluminum_001_Hits
- **LayerSilicon001SdSensitiveDetector**: linked to ['layer_silicon_001'], collection=layer_silicon_001_Hits

## Scoring
- **layer_water_001_edep** (region): edep_MeV
- **layer_water_001_dose** (region): dose_Gy
- **layer_aluminum_001_edep** (region): edep_MeV
- **layer_aluminum_001_dose** (region): dose_Gy
- **layer_silicon_001_edep** (region): edep_MeV
- **layer_silicon_001_dose** (region): dose_Gy
- **layer_water_001_voxel_dose** (voxel): dose_Gy
- **layer_aluminum_001_voxel_dose** (voxel): dose_Gy
- **layer_silicon_001_voxel_dose** (voxel): dose_Gy
- **event_table** (region): edep_MeV, event_id, track_id

## Construction Audit Trail
Total steps: 12
- [evidence_retrieval_node] modify → mir_job_5574e228__20260616_070817: Organized evidence: geometry=1, materials=1, source=1, physics=2, scoring=1
- [model_scope_guard_node] validate → mir_job_5574e228__20260616_070817: Scope guard result: proceed_with_warnings
- [geometry_decomposition_node] create → mir_job_5574e228__20260616_070817: Normalized draft components, 4 components, 3 interfaces
- [coordinate_system_node] modify → mir_job_5574e228__20260616_070817: Set coordinate system: cartesian, origin=world_center
- [material_definition_node] create → mir_job_5574e228__20260616_070817: Defined 4 materials: ['G4_Al', 'G4_Galactic', 'G4_Si', 'G4_WATER']
- [source_definition_node] create → sources: Configured 1 source(s): primary_source:proton 150.0 MeV mono/gun
- [physics_list_node] validate → physics: Preserved drafted physics list: FTFP_BERT
- [sensitive_detector_node] create → sensitive_detectors: Created 3 sensitive detectors for: ['layer_water_001', 'layer_aluminum_001', 'layer_silicon_001']
- [scoring_design_node] create → scoring: Created 10 scoring configurations: ['layer_water_001_edep', 'layer_water_001_dose', 'layer_aluminum_001_edep', 'layer_aluminum_001_dose', 'layer_silicon_001_edep', 'layer_silicon_001_dose', 'layer_water_001_voxel_dose', 'layer_aluminum_001_voxel_dose', 'layer_silicon_001_voxel_dose', 'event_table']
- [model_ir_validation_node] validate → mir_job_5574e228__20260616_070817: Ran 7 validators: 7 passed, 0 errors
- ... and 2 more entries

## Open Issues
- ⚠️ Material thicknesses need confirmation for 150 MeV proton range
- ⚠️ Scoring bin size not specified
- ⚠️ Step limiter settings not specified
