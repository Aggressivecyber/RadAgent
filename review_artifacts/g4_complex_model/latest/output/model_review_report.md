# G4 Model Review: mir_job_919509e8__20260612_201928
- **Job ID**: job_919509e8__20260612_201928
- **Mode**: realistic
- **Target**: 10 MeV proton beam on 300 μm silicon slab detector

## ✅ Validation Status: PASSED

## Geometry Components
| ID | Type | Material | Parent | Sensitive |
|----|------|----------|--------|-----------|
| world | box | G4_AIR | — |  |
| silicon_detector | box | G4_Si | world | ✓ |

## Materials
| ID | Name | Type | Density (g/cm³) |
|----|------|------|-----------------|
| G4_AIR | G4_AIR (NIST) | nist | 0.001225 |
| G4_Si | G4_Si (NIST) | nist | 2.33 |

## Particle Source
- **Particle**: proton
- **Energy**: 10.0 MeV (mono)
- **Events**: 1000
- **Position**: [0.0, 0.0, -800.0] → direction [0.0, 0.0, 1.0]

## Physics
- **List**: QGSP_BIC_HP
- **Reasoning**: User explicitly requested QGSP_BIC_HP for proton transport with high-precision neutron handling.

## Sensitive Detectors
- **SiliconDetectorSdSensitiveDetector**: linked to ['silicon_detector'], collection=silicon_detector_Hits

## Scoring
- **silicon_detector_edep** (region): edep_MeV
- **silicon_detector_dose** (region): dose_Gy
- **silicon_detector_voxel_dose** (voxel): dose_Gy
- **event_table** (region): edep_MeV, event_id, track_id

## Construction Audit Trail
Total steps: 12
- [evidence_retrieval_node] modify → mir_job_919509e8__20260612_201928: Organized evidence: geometry=1, materials=1, source=1, physics=2, scoring=1
- [model_scope_guard_node] validate → mir_job_919509e8__20260612_201928: Scope guard result: proceed_with_warnings
- [geometry_decomposition_node] create → mir_job_919509e8__20260612_201928: Normalized draft components, 2 components, 1 interfaces
- [coordinate_system_node] modify → mir_job_919509e8__20260612_201928: Set coordinate system: cartesian, origin=world_center
- [material_definition_node] create → mir_job_919509e8__20260612_201928: Defined 2 materials: ['G4_AIR', 'G4_Si']
- [source_definition_node] create → sources: Configured 1 source(s): primary_source:proton 10.0 MeV mono/gun
- [physics_list_node] validate → physics: Preserved drafted physics list: QGSP_BIC_HP
- [sensitive_detector_node] create → sensitive_detectors: Created 1 sensitive detectors for: ['silicon_detector']
- [scoring_design_node] create → scoring: Created 4 scoring configurations: ['silicon_detector_edep', 'silicon_detector_dose', 'silicon_detector_voxel_dose', 'event_table']
- [model_ir_validation_node] validate → mir_job_919509e8__20260612_201928: Ran 7 validators: 7 passed, 0 errors
- ... and 2 more entries

## Open Issues
- ⚠️ Source position not specified; assumed at z = -5 mm (world boundary) for vertical incidence.
