# Human Confirmation Report

Readable simulation plan review for human-confirmed Geant4 code generation.

## Task Summary

| Field | Value |
| --- | --- |
| Job ID | job_c528c1f7__20260616_210156 |
| Task | Build a Geant4 shielding study for 14 MeV neutrons through polyethylene, borated polyethylene, lead, and a downstream... |
| Simulation object | world (world), polyethylene (shielding), borated_polyethylene (shielding), lead (shielding), silicon_detector (volume) |
| Domain profile | geant4 |
| Final status | approved |
| Total confirmation rounds | 1 |
| Codegen readiness | READY - code generation can proceed |

## Object, Components, Materials, Sources, Scoring

### Components

| Component | Type | Material | Geometry | Placement | Roles | Confirmation |
| --- | --- | --- | --- | --- | --- | --- |
| world | world | G4_AIR | not specified | {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]} | ["world"] | confirmed by user |
| polyethylene | shielding | G4_POLYETHYLENE | not specified | {"position": [0.0, 0.0, -100000.0], "rotation": [0.0, 0.0, 0.0]} | ["shielding_layer"] | confirmed by user |
| borated_polyethylene | shielding | G4_BORATED_POLYETHYLENE | not specified | {"position": [0.0, 0.0, -50000.0], "rotation": [0.0, 0.0, 0.0]} | ["shielding_layer"] | confirmed by user |
| lead | shielding | G4_Pb | not specified | {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]} | ["shielding_layer"] | confirmed by user |
| silicon_detector | volume | G4_Si | not specified | {"position": [0.0, 0.0, 50000.0], "rotation": [0.0, 0.0, 0.0]} | ["edep_region", "dose_scoring_region"] | confirmed by user |

### Materials

| Material | Used by | Confirmation |
| --- | --- | --- |
| G4_AIR | world | confirmed by user |
| G4_BORATED_POLYETHYLENE | borated_polyethylene | confirmed by user |
| G4_POLYETHYLENE | polyethylene | confirmed by user |
| G4_Pb | lead | confirmed by user |
| G4_Si | silicon_detector | confirmed by user |

### Sources

| ID | Parameters | Confirmation |
| --- | --- | --- |
| primary_source | particle_type=neutron; energy={"distribution": "mono", "sigma": null, "spectrum_file": null, "unit": "MeV", "value":... | confirmed by user |

### Scoring

| ID | Parameters | Confirmation |
| --- | --- | --- |
| event_table | scoring_type=region; quantities=["edep_MeV", "event_id", "track_id"]; voxel_grid=n/a; region_scores=[{"quantity": "ed... | confirmed by user |
| silicon_detector_dose | scoring_type=region; quantities=["dose_Gy"]; voxel_grid=n/a; region_scores=[{"quantity": "dose_Gy", "region_component... | confirmed by user |
| silicon_detector_edep | scoring_type=region; quantities=["edep_MeV"]; voxel_grid=n/a; region_scores=[{"quantity": "edep_MeV", "region_compone... | confirmed by user |
| silicon_detector_voxel_dose | scoring_type=voxel; quantities=["dose_Gy"]; voxel_grid={"target_component_id": "silicon_detector", "voxel_size": [500... | confirmed by user |

## Key Parameter Table

| Parameter | Value | Unit | Source | Confidence | Confirmation |
| --- | --- | --- | --- | --- | --- |
| components.world.placement | {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]} | n/a | assumption | 0.40 | confirmed by user |
| components.world.display_name | World Volume | n/a | assumption | 0.40 | confirmed by user |
| components.world.geometry_type | box | n/a | assumption | 0.40 | confirmed by user |
| components.world.dimensions | {"dx": 1000000.0, "dy": 1000000.0, "dz": 2000000.0} | n/a | assumption | 0.40 | confirmed by user |
| components.world.material_id | G4_AIR | n/a | assumption | 0.40 | confirmed by user |
| components.world.mother_volume | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.world.sensitive | false | n/a | assumption | 0.40 | confirmed by user |
| components.world.color | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.world.source_evidence | ["standard_world"] | n/a | assumption | 0.40 | confirmed by user |
| components.world.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| components.world.requires_confirmation | false | n/a | assumption | 0.40 | confirmed by user |
| components.world.confirmed_by_user | false | n/a | assumption | 0.40 | confirmed by user |
| components.world.confirmation_source | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.polyethylene.placement | {"position": [0.0, 0.0, -100000.0], "rotation": [0.0, 0.0, 0.0]} | n/a | assumption | 0.40 | confirmed by user |
| components.polyethylene.display_name | Polyethylene Shield | n/a | assumption | 0.40 | confirmed by user |
| components.polyethylene.geometry_type | box | n/a | assumption | 0.40 | confirmed by user |
| components.polyethylene.dimensions | {"dx": 100000.0, "dy": 100000.0, "dz": 50000.0} | n/a | assumption | 0.40 | confirmed by user |
| components.polyethylene.material_id | G4_POLYETHYLENE | n/a | assumption | 0.40 | confirmed by user |
| components.polyethylene.mother_volume | world | n/a | assumption | 0.40 | confirmed by user |
| components.polyethylene.sensitive | false | n/a | assumption | 0.40 | confirmed by user |
| components.polyethylene.color | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.polyethylene.source_evidence | ["user_request"] | n/a | assumption | 0.40 | confirmed by user |
| components.polyethylene.open_issues | ["Dimensions (thickness, width, height) for polyethylene layer not specified"] | n/a | assumption | 0.40 | confirmed by user |
| components.polyethylene.requires_confirmation | true | n/a | assumption | 0.40 | confirmed by user |
| components.polyethylene.confirmed_by_user | false | n/a | assumption | 0.40 | confirmed by user |
| components.polyethylene.confirmation_source | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.borated_polyethylene.placement | {"position": [0.0, 0.0, -50000.0], "rotation": [0.0, 0.0, 0.0]} | n/a | assumption | 0.40 | confirmed by user |
| components.borated_polyethylene.display_name | Borated Polyethylene Shield | n/a | assumption | 0.40 | confirmed by user |
| components.borated_polyethylene.geometry_type | box | n/a | assumption | 0.40 | confirmed by user |
| components.borated_polyethylene.dimensions | {"dx": 100000.0, "dy": 100000.0, "dz": 50000.0} | n/a | assumption | 0.40 | confirmed by user |
| components.borated_polyethylene.material_id | G4_BORATED_POLYETHYLENE | n/a | assumption | 0.40 | confirmed by user |
| components.borated_polyethylene.mother_volume | world | n/a | assumption | 0.40 | confirmed by user |
| components.borated_polyethylene.sensitive | false | n/a | assumption | 0.40 | confirmed by user |
| components.borated_polyethylene.color | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.borated_polyethylene.source_evidence | ["user_request"] | n/a | assumption | 0.40 | confirmed by user |
| components.borated_polyethylene.open_issues | ["Dimensions for borated polyethylene layer not specified"] | n/a | assumption | 0.40 | confirmed by user |
| components.borated_polyethylene.requires_confirmation | true | n/a | assumption | 0.40 | confirmed by user |
| components.borated_polyethylene.confirmed_by_user | false | n/a | assumption | 0.40 | confirmed by user |
| components.borated_polyethylene.confirmation_source | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.lead.placement | {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]} | n/a | assumption | 0.40 | confirmed by user |
| components.lead.display_name | Lead Shield | n/a | assumption | 0.40 | confirmed by user |
| components.lead.geometry_type | box | n/a | assumption | 0.40 | confirmed by user |
| components.lead.dimensions | {"dx": 100000.0, "dy": 100000.0, "dz": 20000.0} | n/a | assumption | 0.40 | confirmed by user |
| components.lead.material_id | G4_Pb | n/a | assumption | 0.40 | confirmed by user |
| components.lead.mother_volume | world | n/a | assumption | 0.40 | confirmed by user |
| components.lead.sensitive | false | n/a | assumption | 0.40 | confirmed by user |
| components.lead.color | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.lead.source_evidence | ["user_request"] | n/a | assumption | 0.40 | confirmed by user |
| components.lead.open_issues | ["Dimensions for lead layer not specified"] | n/a | assumption | 0.40 | confirmed by user |
| components.lead.requires_confirmation | true | n/a | assumption | 0.40 | confirmed by user |
| components.lead.confirmed_by_user | false | n/a | assumption | 0.40 | confirmed by user |
| components.lead.confirmation_source | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.placement | {"position": [0.0, 0.0, 50000.0], "rotation": [0.0, 0.0, 0.0]} | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.display_name | Silicon Detector | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.geometry_type | box | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.dimensions | {"dx": 50000.0, "dy": 50000.0, "dz": 500.0} | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.material_id | G4_Si | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.mother_volume | world | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.sensitive | true | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.color | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.source_evidence | ["user_request", "metadata_target_material_hint"] | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.open_issues | ["Dimensions for silicon detector not specified"] | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.requires_confirmation | true | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.confirmed_by_user | false | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.confirmation_source | n/a | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.particle_type | neutron | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.energy | {"distribution": "mono", "sigma": null, "spectrum_file": null, "unit": "MeV", "value": 14.0} | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.beam | {"angular_distribution": "mono", "angular_spectrum_file": null, "direction": [0.0, 0.0, 1.0], "position": [0.0, 0.0,... | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.generator_type | gun | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.events | 1000 | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.relative_weight | n/a | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.source_evidence | ["task_spec.particles[0]: source_id=primary_source, particle=neutron, energy=14.0 MeV, distribution=mono, generator=g... | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_edep.scoring_type | region | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_edep.quantities | ["edep_MeV"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_edep.voxel_grid | n/a | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_edep.region_scores | [{"quantity": "edep_MeV", "region_component_id": "silicon_detector"}] | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_edep.output_format | csv | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_edep.source_evidence | ["Auto-generated: region edep scoring for silicon_detector"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_edep.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_dose.scoring_type | region | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_dose.quantities | ["dose_Gy"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_dose.voxel_grid | n/a | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_dose.region_scores | [{"quantity": "dose_Gy", "region_component_id": "silicon_detector"}] | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_dose.output_format | csv | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_dose.source_evidence | ["Auto-generated: region dose scoring for silicon_detector"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_dose.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_voxel_dose.scoring_type | voxel | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_voxel_dose.quantities | ["dose_Gy"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_voxel_dose.voxel_grid | {"target_component_id": "silicon_detector", "voxel_size": [5000.0, 5000.0, 50.0]} | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_voxel_dose.region_scores | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_voxel_dose.output_format | csv | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_voxel_dose.source_evidence | ["Auto-generated: voxel dose map for silicon_detector, voxel_size=[5000.0, 5000.0, 50.0] um"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_voxel_dose.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.scoring_type | region | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.quantities | ["edep_MeV", "event_id", "track_id"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.voxel_grid | n/a | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.region_scores | [{"quantity": "edep_MeV", "region_component_id": "silicon_detector"}] | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.output_format | csv | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.source_evidence | ["Auto-generated: event table for all sensitive components"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |

## Assumptions and Risks

### Missing Information
- Geometry dimensions not specified for any component
- Layer order not confirmed
- Source position not specified
- Number of events not specified
- Scoring methods not detailed
- Dimensions (thickness, width, height) for polyethylene layer not specified
- Dimensions for borated polyethylene layer not specified
- Dimensions for lead layer not specified
- Dimensions for silicon detector not specified

### Risks
- No blocking risks recorded in human confirmation artifacts.

## Required User Actions

- No additional user action is required before code generation.

## Confirmation History

| Round | Decision | Edits | Notes |
| --- | --- | --- | --- |
| 1 | approve | none | n/a |

## Codegen Readiness

| Check | Result |
| --- | --- |
| Readiness decision | READY - code generation can proceed |
| Reason | Human confirmation completed and confirmed model plan is available. |
| Confirmation status | approved |
| Confirmed plan status | approved |
| Unconfirmed assumptions | 0 |
| Remaining unconfirmed fields | 0 |
| Confirmed model plan | simulation_workspace/jobs/job_c528c1f7__20260616_210156/04_human_confirmation/confirmed_model_plan.json |
