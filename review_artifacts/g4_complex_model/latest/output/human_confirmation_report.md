# Human Confirmation Report

Readable simulation plan review for human-confirmed Geant4 code generation.

## Task Summary

| Field | Value |
| --- | --- |
| Job ID | job_919509e8__20260612_201928 |
| Task | 建立 Geant4 仿真项目：10 MeV 单能质子束垂直入射 300 μm 厚硅平板探测器（横向 10 mm x 10 mm），运行 1000 个事件。使用 QGSP_BIC_HP 物理列表。记录每个事件的总能量沉积以及沿入射方向的... |
| Simulation object | world (world), silicon_detector (volume) |
| Domain profile | geant4 |
| Final status | approved |
| Total confirmation rounds | 1 |
| Codegen readiness | READY - code generation can proceed |

## Object, Components, Materials, Sources, Scoring

### Components

| Component | Type | Material | Geometry | Placement | Roles | Confirmation |
| --- | --- | --- | --- | --- | --- | --- |
| world | world | G4_AIR | not specified | {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]} | [] | confirmed by user |
| silicon_detector | volume | G4_Si | not specified | {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]} | ["edep_region", "dose_scoring_region"] | confirmed by user |

### Materials

| Material | Used by | Confirmation |
| --- | --- | --- |
| G4_AIR | world | confirmed by user |
| G4_Si | silicon_detector | confirmed by user |

### Sources

| ID | Parameters | Confirmation |
| --- | --- | --- |
| primary_source | particle_type=proton; energy={"distribution": "mono", "sigma": null, "spectrum_file": null, "unit": "MeV", "value": 1... | confirmed by user |

### Scoring

| ID | Parameters | Confirmation |
| --- | --- | --- |
| event_table | scoring_type=region; quantities=["edep_MeV", "event_id", "track_id"]; voxel_grid=n/a; region_scores=[{"quantity": "ed... | confirmed by user |
| silicon_detector_dose | scoring_type=region; quantities=["dose_Gy"]; voxel_grid=n/a; region_scores=[{"quantity": "dose_Gy", "region_component... | confirmed by user |
| silicon_detector_edep | scoring_type=region; quantities=["edep_MeV"]; voxel_grid=n/a; region_scores=[{"quantity": "edep_MeV", "region_compone... | confirmed by user |
| silicon_detector_voxel_dose | scoring_type=voxel; quantities=["dose_Gy"]; voxel_grid={"target_component_id": "silicon_detector", "voxel_size": [100... | confirmed by user |

## Key Parameter Table

| Parameter | Value | Unit | Source | Confidence | Confirmation |
| --- | --- | --- | --- | --- | --- |
| components.world.display_name | World Volume | n/a | assumption | 0.40 | confirmed by user |
| components.world.geometry_type | box | n/a | assumption | 0.40 | confirmed by user |
| components.world.dimensions | {"dx": 50000.0, "dy": 50000.0, "dz": 10000.0} | n/a | assumption | 0.40 | confirmed by user |
| components.world.material_id | G4_AIR | n/a | assumption | 0.40 | confirmed by user |
| components.world.mother_volume | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.world.sensitive | false | n/a | assumption | 0.40 | confirmed by user |
| components.world.color | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.world.source_evidence | ["User request: world volume 50x50x10 mm\u00b3 air"] | n/a | assumption | 0.40 | confirmed by user |
| components.world.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| components.world.requires_confirmation | false | n/a | assumption | 0.40 | confirmed by user |
| components.world.confirmed_by_user | false | n/a | assumption | 0.40 | confirmed by user |
| components.world.confirmation_source | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.display_name | Silicon Slab Detector | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.geometry_type | box | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.dimensions | {"dx": 10000.0, "dy": 10000.0, "dz": 300.0} | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.material_id | G4_Si | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.mother_volume | world | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.sensitive | true | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.color | n/a | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.source_evidence | ["User request: 300 \u03bcm thick silicon slab, 10 mm x 10 mm lateral"] | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.requires_confirmation | false | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.confirmed_by_user | false | n/a | assumption | 0.40 | confirmed by user |
| components.silicon_detector.confirmation_source | n/a | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.particle_type | proton | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.energy | {"distribution": "mono", "sigma": null, "spectrum_file": null, "unit": "MeV", "value": 10.0} | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.beam | {"angular_distribution": "mono", "angular_spectrum_file": null, "direction": [0.0, 0.0, 1.0], "position": [0.0, 0.0,... | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.generator_type | gun | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.events | 1000 | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.relative_weight | n/a | n/a | assumption | 0.40 | confirmed by user |
| sources.primary_source.source_evidence | ["task_spec.particles[0]: source_id=primary_source, particle=proton, energy=10.0 MeV, distribution=mono, generator=gu... | n/a | assumption | 0.40 | confirmed by user |
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
| scoring.silicon_detector_voxel_dose.voxel_grid | {"target_component_id": "silicon_detector", "voxel_size": [1000.0, 1000.0, 30.0]} | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_voxel_dose.region_scores | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_voxel_dose.output_format | csv | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_voxel_dose.source_evidence | ["Auto-generated: voxel dose map for silicon_detector, voxel_size=[1000.0, 1000.0, 30.0] um"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.silicon_detector_voxel_dose.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.scoring_type | region | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.quantities | ["edep_MeV", "event_id", "track_id"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.voxel_grid | n/a | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.region_scores | [{"quantity": "edep_MeV", "region_component_id": "silicon_detector"}] | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.output_format | csv | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.source_evidence | ["Auto-generated: event table for all sensitive components"] | n/a | assumption | 0.40 | confirmed by user |
| scoring.event_table.open_issues | [] | n/a | assumption | 0.40 | confirmed by user |

## Assumptions and Risks

### Risks
- No blocking risks recorded in human confirmation artifacts.

## Required User Actions

- No additional user action is required before code generation.

## Confirmation History

| Round | Decision | Edits | Notes |
| --- | --- | --- | --- |
| 1 | approve | none | Approved before pipeline start through RadAgent briefing. |

## Codegen Readiness

| Check | Result |
| --- | --- |
| Readiness decision | READY - code generation can proceed |
| Reason | Human confirmation completed and confirmed model plan is available. |
| Confirmation status | approved |
| Confirmed plan status | approved |
| Unconfirmed assumptions | 0 |
| Remaining unconfirmed fields | 0 |
| Confirmed model plan | /tmp/radagent_tui_full_5e5p2w2h/jobs/job_919509e8__20260612_201928/04_human_confirmation/confirmed_model_plan.json |
