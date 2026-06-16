# Human Confirmation Report

Readable simulation plan review for human-confirmed Geant4 code generation.

## Task Summary

| Field | Value |
| --- | --- |
| Job ID | job_5574e228__20260616_070817 |
| Task | Build a Geant4 proton depth-dose benchmark for a 150 MeV pencil beam through water, aluminum, and silicon layers. Pro... |
| Simulation object | world_001 (world), layer_water_001 (layer), layer_aluminum_001 (layer), layer_silicon_001 (layer) |
| Domain profile | geant4 |
| Final status | approved |
| Total confirmation rounds | 1 |
| Codegen readiness | READY - code generation can proceed |

## Object, Components, Materials, Sources, Scoring

### Components

| Component | Type | Material | Geometry | Placement | Roles | Confirmation |
| --- | --- | --- | --- | --- | --- | --- |
| world_001 | world | G4_Galactic | not specified | {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]} | ["world"] | confirmed by user |
| layer_water_001 | layer | G4_WATER | not specified | {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]} | ["edep_region", "dose_scoring_region"] | confirmed by user |
| layer_aluminum_001 | layer | G4_Al | not specified | {"position": [0.0, 0.0, 300000.0], "rotation": [0.0, 0.0, 0.0]} | ["edep_region", "dose_scoring_region"] | confirmed by user |
| layer_silicon_001 | layer | G4_Si | not specified | {"position": [0.0, 0.0, 350000.0], "rotation": [0.0, 0.0, 0.0]} | ["edep_region", "dose_scoring_region"] | confirmed by user |

### Materials

| Material | Used by | Confirmation |
| --- | --- | --- |
| G4_Al | layer_aluminum_001 | confirmed by user |
| G4_Galactic | world_001 | confirmed by user |
| G4_Si | layer_silicon_001 | confirmed by user |
| G4_WATER | layer_water_001 | confirmed by user |

### Sources

| ID | Parameters | Confirmation |
| --- | --- | --- |
| primary_source | particle_type=proton; energy={"distribution": "mono", "sigma": null, "spectrum_file": null, "unit": "MeV", "value": 1... | confirmed by user |

### Scoring

| ID | Parameters | Confirmation |
| --- | --- | --- |
| event_table | scoring_type=region; quantities=["edep_MeV", "event_id", "track_id"]; voxel_grid=n/a; region_scores=[{"quantity": "ed... | confirmed by user |
| layer_aluminum_001_dose | scoring_type=region; quantities=["dose_Gy"]; voxel_grid=n/a; region_scores=[{"quantity": "dose_Gy", "region_component... | confirmed by user |
| layer_aluminum_001_edep | scoring_type=region; quantities=["edep_MeV"]; voxel_grid=n/a; region_scores=[{"quantity": "edep_MeV", "region_compone... | confirmed by user |
| layer_aluminum_001_voxel_dose | scoring_type=voxel; quantities=["dose_Gy"]; voxel_grid={"target_component_id": "layer_aluminum_001", "voxel_size": [1... | confirmed by user |
| layer_silicon_001_dose | scoring_type=region; quantities=["dose_Gy"]; voxel_grid=n/a; region_scores=[{"quantity": "dose_Gy", "region_component... | confirmed by user |
| layer_silicon_001_edep | scoring_type=region; quantities=["edep_MeV"]; voxel_grid=n/a; region_scores=[{"quantity": "edep_MeV", "region_compone... | confirmed by user |
| layer_silicon_001_voxel_dose | scoring_type=voxel; quantities=["dose_Gy"]; voxel_grid={"target_component_id": "layer_silicon_001", "voxel_size": [10... | confirmed by user |
| layer_water_001_dose | scoring_type=region; quantities=["dose_Gy"]; voxel_grid=n/a; region_scores=[{"quantity": "dose_Gy", "region_component... | confirmed by user |
| layer_water_001_edep | scoring_type=region; quantities=["edep_MeV"]; voxel_grid=n/a; region_scores=[{"quantity": "edep_MeV", "region_compone... | confirmed by user |
| layer_water_001_voxel_dose | scoring_type=voxel; quantities=["dose_Gy"]; voxel_grid={"target_component_id": "layer_water_001", "voxel_size": [1000... | confirmed by user |

## Key Parameter Table

| Parameter | Value | Unit | Source | Confidence | Confirmation |
| --- | --- | --- | --- | --- | --- |
| components.world_001.placement | {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]} | n/a | assumption | 0.40 | confirmed by user |
| components.world_001.display_name | World Volume | n/a | assumption | 0.40 | confirmed by user |
| components.world_001.geometry_type | box | n/a | assumption | 0.40 | confirmed by user |
| components.world_001.dimensions | {"dx": 100000.0, "dy": 100000.0, "dz": 752000.0} | n/a | assumption | 0.40 | confirmed by user |
| components.world_001.material_id | G4_Galactic | n/a | assumption | 0.40 | confirmed by user |
| components.world_001.mother_volume | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.world_001.sensitive | false | n/a | assumption | 0.40 | confirmed by user |
| components.world_001.color | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.world_001.source_evidence | ["Standard Geant4 world volume", "geometry_decomposition:expanded mother volume to contain daughter placements on z"] | n/a | assumption | 0.40 | confirmed by user |
| components.world_001.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| components.world_001.requires_confirmation | false | n/a | assumption | 0.40 | confirmed by user |
| components.world_001.confirmed_by_user | false | n/a | assumption | 0.40 | confirmed by user |
| components.world_001.confirmation_source | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.layer_water_001.placement | {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]} | n/a | assumption | 0.40 | confirmed by user |
| components.layer_water_001.display_name | Water Layer | n/a | assumption | 0.40 | confirmed by user |
| components.layer_water_001.geometry_type | box | n/a | assumption | 0.40 | confirmed by user |
| components.layer_water_001.dimensions | {"dx": 10000.0, "dy": 10000.0, "dz": 300000.0} | n/a | assumption | 0.40 | confirmed by user |
| components.layer_water_001.material_id | G4_WATER | n/a | assumption | 0.40 | confirmed by user |
| components.layer_water_001.mother_volume | world_001 | n/a | assumption | 0.40 | confirmed by user |
| components.layer_water_001.sensitive | true | n/a | assumption | 0.40 | confirmed by user |
| components.layer_water_001.color | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.layer_water_001.source_evidence | ["Water phantom for proton therapy benchmark"] | n/a | assumption | 0.40 | confirmed by user |
| components.layer_water_001.open_issues | ["Material thickness needs confirmation for 150 MeV proton range"] | n/a | assumption | 0.40 | confirmed by user |
| components.layer_water_001.requires_confirmation | true | n/a | assumption | 0.40 | confirmed by user |
| components.layer_water_001.confirmed_by_user | false | n/a | assumption | 0.40 | confirmed by user |
| components.layer_water_001.confirmation_source | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.layer_aluminum_001.placement | {"position": [0.0, 0.0, 300000.0], "rotation": [0.0, 0.0, 0.0]} | n/a | assumption | 0.40 | confirmed by user |
| components.layer_aluminum_001.display_name | Aluminum Layer | n/a | assumption | 0.40 | confirmed by user |
| components.layer_aluminum_001.geometry_type | box | n/a | assumption | 0.40 | confirmed by user |
| components.layer_aluminum_001.dimensions | {"dx": 10000.0, "dy": 10000.0, "dz": 50000.0} | n/a | assumption | 0.40 | confirmed by user |
| components.layer_aluminum_001.material_id | G4_Al | n/a | assumption | 0.40 | confirmed by user |
| components.layer_aluminum_001.mother_volume | world_001 | n/a | assumption | 0.40 | confirmed by user |
| components.layer_aluminum_001.sensitive | true | n/a | assumption | 0.40 | confirmed by user |
| components.layer_aluminum_001.color | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.layer_aluminum_001.source_evidence | ["Aluminum layer for material variation study"] | n/a | assumption | 0.40 | confirmed by user |
| components.layer_aluminum_001.open_issues | ["Material thickness needs confirmation"] | n/a | assumption | 0.40 | confirmed by user |
| components.layer_aluminum_001.requires_confirmation | true | n/a | assumption | 0.40 | confirmed by user |
| components.layer_aluminum_001.confirmed_by_user | false | n/a | assumption | 0.40 | confirmed by user |
| components.layer_aluminum_001.confirmation_source | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.layer_silicon_001.placement | {"position": [0.0, 0.0, 350000.0], "rotation": [0.0, 0.0, 0.0]} | n/a | assumption | 0.40 | confirmed by user |
| components.layer_silicon_001.display_name | Silicon Layer | n/a | assumption | 0.40 | confirmed by user |
| components.layer_silicon_001.geometry_type | box | n/a | assumption | 0.40 | confirmed by user |
| components.layer_silicon_001.dimensions | {"dx": 10000.0, "dy": 10000.0, "dz": 50000.0} | n/a | assumption | 0.40 | confirmed by user |
| components.layer_silicon_001.material_id | G4_Si | n/a | assumption | 0.40 | confirmed by user |
| components.layer_silicon_001.mother_volume | world_001 | n/a | assumption | 0.40 | confirmed by user |
| components.layer_silicon_001.sensitive | true | n/a | assumption | 0.40 | confirmed by user |
| components.layer_silicon_001.color | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.layer_silicon_001.source_evidence | ["Silicon layer for detector material study"] | n/a | assumption | 0.40 | confirmed by user |
| components.layer_silicon_001.open_issues | ["Material thickness needs confirmation"] | n/a | assumption | 0.40 | confirmed by user |
| components.layer_silicon_001.requires_confirmation | true | n/a | assumption | 0.40 | confirmed by user |
| components.layer_silicon_001.confirmed_by_user | false | n/a | assumption | 0.40 | confirmed by user |
| components.layer_silicon_001.confirmation_source | n/a | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.particle_type | proton | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.energy | {"distribution": "mono", "sigma": null, "spectrum_file": null, "unit": "MeV", "value": 150.0} | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.beam | {"angular_distribution": "mono", "angular_spectrum_file": null, "direction": [0.0, 0.0, 1.0], "position": [0.0, 0.0,... | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.generator_type | gun | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.events | 1000 | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.relative_weight | n/a | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.source_evidence | ["task_spec.particles[0]: source_id=primary_source, particle=proton, energy=150.0 MeV, distribution=mono, generator=g... | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_edep.scoring_type | region | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_edep.quantities | ["edep_MeV"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_edep.voxel_grid | n/a | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_edep.region_scores | [{"quantity": "edep_MeV", "region_component_id": "layer_water_001"}] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_edep.output_format | csv | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_edep.source_evidence | ["Auto-generated: region edep scoring for layer_water_001"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_edep.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_dose.scoring_type | region | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_dose.quantities | ["dose_Gy"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_dose.voxel_grid | n/a | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_dose.region_scores | [{"quantity": "dose_Gy", "region_component_id": "layer_water_001"}] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_dose.output_format | csv | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_dose.source_evidence | ["Auto-generated: region dose scoring for layer_water_001"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_dose.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_edep.scoring_type | region | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_edep.quantities | ["edep_MeV"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_edep.voxel_grid | n/a | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_edep.region_scores | [{"quantity": "edep_MeV", "region_component_id": "layer_aluminum_001"}] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_edep.output_format | csv | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_edep.source_evidence | ["Auto-generated: region edep scoring for layer_aluminum_001"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_edep.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_dose.scoring_type | region | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_dose.quantities | ["dose_Gy"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_dose.voxel_grid | n/a | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_dose.region_scores | [{"quantity": "dose_Gy", "region_component_id": "layer_aluminum_001"}] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_dose.output_format | csv | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_dose.source_evidence | ["Auto-generated: region dose scoring for layer_aluminum_001"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_dose.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_edep.scoring_type | region | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_edep.quantities | ["edep_MeV"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_edep.voxel_grid | n/a | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_edep.region_scores | [{"quantity": "edep_MeV", "region_component_id": "layer_silicon_001"}] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_edep.output_format | csv | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_edep.source_evidence | ["Auto-generated: region edep scoring for layer_silicon_001"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_edep.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_dose.scoring_type | region | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_dose.quantities | ["dose_Gy"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_dose.voxel_grid | n/a | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_dose.region_scores | [{"quantity": "dose_Gy", "region_component_id": "layer_silicon_001"}] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_dose.output_format | csv | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_dose.source_evidence | ["Auto-generated: region dose scoring for layer_silicon_001"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_dose.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_voxel_dose.scoring_type | voxel | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_voxel_dose.quantities | ["dose_Gy"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_voxel_dose.voxel_grid | {"target_component_id": "layer_water_001", "voxel_size": [1000.0, 1000.0, 30000.0]} | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_voxel_dose.region_scores | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_voxel_dose.output_format | csv | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_voxel_dose.source_evidence | ["Auto-generated: voxel dose map for layer_water_001, voxel_size=[1000.0, 1000.0, 30000.0] um"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_water_001_voxel_dose.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_voxel_dose.scoring_type | voxel | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_voxel_dose.quantities | ["dose_Gy"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_voxel_dose.voxel_grid | {"target_component_id": "layer_aluminum_001", "voxel_size": [1000.0, 1000.0, 5000.0]} | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_voxel_dose.region_scores | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_voxel_dose.output_format | csv | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_voxel_dose.source_evidence | ["Auto-generated: voxel dose map for layer_aluminum_001, voxel_size=[1000.0, 1000.0, 5000.0] um"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_aluminum_001_voxel_dose.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_voxel_dose.scoring_type | voxel | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_voxel_dose.quantities | ["dose_Gy"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_voxel_dose.voxel_grid | {"target_component_id": "layer_silicon_001", "voxel_size": [1000.0, 1000.0, 5000.0]} | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_voxel_dose.region_scores | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_voxel_dose.output_format | csv | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_voxel_dose.source_evidence | ["Auto-generated: voxel dose map for layer_silicon_001, voxel_size=[1000.0, 1000.0, 5000.0] um"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.layer_silicon_001_voxel_dose.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.scoring_type | region | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.quantities | ["edep_MeV", "event_id", "track_id"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.voxel_grid | n/a | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.region_scores | [{"quantity": "edep_MeV", "region_component_id": "layer_water_001"}, {"quantity": "edep_MeV", "region_component_id":... | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.output_format | csv | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.source_evidence | ["Auto-generated: event table for all sensitive components"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |

## Assumptions and Risks

### Missing Information
- Material thicknesses need confirmation for 150 MeV proton range
- Scoring bin size not specified
- Step limiter settings not specified
- Material thickness needs confirmation for 150 MeV proton range
- Material thickness needs confirmation

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
| Confirmed model plan | simulation_workspace/jobs/job_5574e228__20260616_070817/04_human_confirmation/confirmed_model_plan.json |
