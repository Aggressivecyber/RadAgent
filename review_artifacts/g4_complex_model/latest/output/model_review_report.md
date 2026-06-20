# G4 Model Review: mir_job_87aa0262__20260620_151324
- **Job ID**: job_87aa0262__20260620_151324
- **Mode**: realistic
- **Target**: Geant4 shielding study for 14 MeV neutrons through polyethylene, borated polyethylene, lead, and a downstream silicon detector.

## ✅ Validation Status: PASSED

## Geometry Components
| ID | Type | Material | Parent | Sensitive |
|----|------|----------|--------|-----------|
| world | cylinder | G4_AIR | — |  |
| polyethylene_layer | cylinder | G4_POLYETHYLENE | world |  |
| borated_polyethylene_layer | cylinder | G4_BORATED_POLYETHYLENE_5Percent | world |  |
| lead_layer | cylinder | G4_Pb | world |  |
| silicon_detector | cylinder | G4_Si | world | ✓ |

## Materials
| ID | Name | Type | Density (g/cm³) |
|----|------|------|-----------------|
| G4_AIR | G4_AIR (NIST) | nist | 0.001225 |
| G4_BORATED_POLYETHYLENE_5Percent | Material pending user selection: G4_BORATED_POLYETHYLENE_5Percent | custom | 2.33 |
| G4_POLYETHYLENE | Polyethylene | custom | 0.94 |
| G4_Pb | G4_Pb (NIST) | nist | 11.35 |
| G4_Si | G4_Si (NIST) | nist | 2.33 |

## Particle Source
- **Particle**: neutron
- **Energy**: 14.0 MeV (mono)
- **Events**: 1000
- **Position**: [0.0, 0.0, -180950.0] → direction [0.0, 0.0, 1.0]

## Physics
- **List**: Shielding
- **Reasoning**: The 'Shielding' physics list is specifically designed for neutron shielding studies, including low-energy neutron transport and secondary particle production, which matches the user's request for a shielding study with neutron leakage and secondary gamma scoring.

## Sensitive Detectors
- **SiliconDetectorSdSensitiveDetector**: linked to ['silicon_detector'], collection=silicon_detector_Hits

## Scoring
- **silicon_detector_edep** (region): edep_MeV
- **silicon_detector_dose** (region): dose_Gy
- **silicon_detector_voxel_dose** (voxel): dose_Gy
- **event_table** (region): edep_MeV, event_id, track_id

## Construction Audit Trail
Total steps: 12
- [evidence_retrieval_node] modify → mir_job_87aa0262__20260620_151324: Organized evidence: geometry=1, materials=1, source=2, physics=2, scoring=2
- [model_scope_guard_node] validate → mir_job_87aa0262__20260620_151324: Scope guard result: proceed_with_warnings
- [geometry_decomposition_node] create → mir_job_87aa0262__20260620_151324: Normalized draft components, 5 components, 4 interfaces
- [coordinate_system_node] modify → mir_job_87aa0262__20260620_151324: Set coordinate system: cartesian, origin=world_center
- [material_definition_node] create → mir_job_87aa0262__20260620_151324: Defined 5 materials: ['G4_AIR', 'G4_BORATED_POLYETHYLENE_5Percent', 'G4_POLYETHYLENE', 'G4_Pb', 'G4_Si']
- [source_definition_node] create → sources: Configured 1 source(s): primary_source:neutron 14.0 MeV mono/gun
- [physics_list_node] validate → physics: Preserved drafted physics list: Shielding
- [sensitive_detector_node] create → sensitive_detectors: Created 1 sensitive detectors for: ['silicon_detector']
- [scoring_design_node] create → scoring: Created 4 scoring configurations: ['silicon_detector_edep', 'silicon_detector_dose', 'silicon_detector_voxel_dose', 'event_table']
- [model_ir_validation_node] validate → mir_job_87aa0262__20260620_151324: Ran 7 validators: 7 passed, 0 errors
- ... and 2 more entries
