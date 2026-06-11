from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from agent_core.g4_modeling.nodes.source_definition_node import source_definition_node
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
from agent_core.g4_modeling.schemas.source_spec import SourceSpec
from agent_core.space_radiation.ap8ae8_provider import (
    AEP8RuntimeFluxEvaluator,
    GeodeticOrbitSample,
    OrbitRadiationRequest,
    SpaceRadiationProvider,
    is_orbit_radiation_request,
)
from knowledge_base.space_radiation.ap8ae8 import AP8AE8_DATASET_ID


def test_orbit_radiation_intent_detection_supports_chinese_and_english() -> None:
    assert is_orbit_radiation_request("仿真 500km 太阳同步轨道的空间辐照")
    assert is_orbit_radiation_request("simulate trapped belt dose using AP8 AE8")
    assert is_orbit_radiation_request("Van Allen electron radiation for L shell")
    assert not is_orbit_radiation_request("simulate a 10 MeV proton beam in silicon")


def test_request_reports_missing_fields_for_altitude_only_orbit(tmp_path: Path) -> None:
    provider = SpaceRadiationProvider(data_dir=tmp_path)
    request = OrbitRadiationRequest(
        particle="proton",
        solar_period="min",
        altitude_km=500.0,
        inclination_deg=97.6,
    )

    report = provider.validate_request(request)

    assert report.ready is False
    assert "l_shell" in report.missing_fields
    assert "bb0" in report.missing_fields
    assert "altitude/inclination" in " ".join(report.notes)


def test_geodetic_orbit_sample_is_complete_environment_without_l_shell(tmp_path: Path) -> None:
    provider = SpaceRadiationProvider(data_dir=tmp_path)
    request = OrbitRadiationRequest(
        particle="proton",
        solar_period="min",
        geodetic_samples=[
            GeodeticOrbitSample(
                latitude_deg=0.0,
                longitude_deg=120.0,
                altitude_km=500.0,
                iso_time="2026-06-11T00:00:00",
            )
        ],
    )

    report = provider.validate_request(request)

    assert report.ready is True
    assert "l_shell" not in report.missing_fields
    assert "bb0" not in report.missing_fields


def test_tle_orbit_request_is_complete_environment_without_l_shell(tmp_path: Path) -> None:
    provider = SpaceRadiationProvider(data_dir=tmp_path)
    request = OrbitRadiationRequest(
        particle="proton",
        solar_period="min",
        tle_lines=(
            "1 25544U 98067A   26162.00000000  .00016717  00000+0  10270-3 0  9000",
            "2 25544  51.6400 120.0000 0006000  80.0000  40.0000 15.50000000 00001",
        ),
        start_time="2026-06-11T00:00:00Z",
        stop_time="2026-06-11T00:10:00Z",
        sample_count=3,
    )

    report = provider.validate_request(request)

    assert report.ready is True
    assert "l_shell" not in report.missing_fields
    assert "bb0" not in report.missing_fields


@pytest.mark.parametrize(
    ("particle", "solar_period", "expected_model"),
    [
        ("proton", "min", "AP8MIN"),
        ("proton", "max", "AP8MAX"),
        ("electron", "min", "AE8MIN"),
        ("e-", "max", "AE8MAX"),
    ],
)
def test_model_selection_maps_particle_and_solar_period(
    particle: str,
    solar_period: str,
    expected_model: str,
    tmp_path: Path,
) -> None:
    provider = SpaceRadiationProvider(data_dir=tmp_path)
    request = OrbitRadiationRequest(
        particle=particle,
        solar_period=solar_period,
        l_shell=2.4,
        bb0=1.1,
    )

    assert provider.select_model(request) == expected_model


def test_create_source_package_writes_spectrum_and_task_particle(tmp_path: Path) -> None:
    class _Evaluator:
        def flux(
            self,
            *,
            model_name: str,
            energy_mev: float,
            request: OrbitRadiationRequest,
        ) -> float:
            assert model_name == "AP8MIN"
            assert request.l_shell == 2.0
            return energy_mev * 100.0

    provider = SpaceRadiationProvider(data_dir=tmp_path, flux_evaluator=_Evaluator())
    request = OrbitRadiationRequest(
        particle="proton",
        solar_period="min",
        l_shell=2.0,
        bb0=1.05,
        flux_mode="differential",
        events=2500,
        source_id="leo_trapped_protons",
    )

    package = provider.create_source_package(request, output_dir=tmp_path / "spectra")

    assert package.model_name == "AP8MIN"
    assert package.dataset_id == AP8AE8_DATASET_ID
    assert package.spectrum_file.is_file()
    text = package.spectrum_file.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "energy_MeV,flux_cm-2_s-1_MeV-1"
    assert "1,100" in text
    assert "2.0" in package.evidence[1]

    particle = package.to_task_particle()
    assert particle["source_id"] == "leo_trapped_protons"
    assert particle["type"] == "proton"
    assert particle["energy_distribution"] == "spectrum"
    assert particle["spectrum_file"] == str(package.spectrum_file)
    assert particle["generator_type"] == "gps"
    assert particle["events"] == 2500
    assert particle["source_evidence"] == package.evidence

    external_source = package.to_external_source()
    assert external_source["source_id"] == "leo_trapped_protons"
    assert external_source["source_type"] == "environment"
    assert external_source["domain"] == "space_radiation"
    assert external_source["provider"] == "ap8ae8"
    assert external_source["model"] == "AP8MIN"
    assert external_source["status"] == "ready"
    assert external_source["artifact_paths"] == [str(package.spectrum_file)]
    assert external_source["parameters"]["flux_mode"] == "differential"
    assert external_source["provenance"]["dataset_id"] == AP8AE8_DATASET_ID
    assert external_source["derived_outputs"][0]["consumer"] == "g4_modeling"


def test_source_definition_preserves_ap8ae8_source_evidence(tmp_path: Path) -> None:
    spectrum = tmp_path / "ap8min_spectrum.csv"
    spectrum.write_text("energy_MeV,flux_cm-2_s-1_MeV-1\n1,10\n", encoding="utf-8")
    model_ir = G4ModelIR(
        model_ir_id="model_1",
        job_id="job_1",
        components=[],
    )
    evidence = [
        "AP8/AE8 dataset nasa-radbelt-aep8 model AP8MIN",
        "magnetic coordinates L=2.0 B/B0=1.05",
    ]

    result = asyncio.run(
        source_definition_node(
        {
            "g4_model_ir": model_ir.model_dump(mode="json"),
            "task_spec": {
                "particles": [
                    {
                        "source_id": "leo_trapped_protons",
                        "type": "proton",
                        "energy_MeV": 1.0,
                        "energy_distribution": "spectrum",
                        "spectrum_file": str(spectrum),
                        "events": 100,
                        "source_evidence": evidence,
                    }
                ]
            },
        }
        )
    )
    source = SourceSpec.model_validate(result["g4_model_ir"]["sources"][0])

    assert source.source_evidence == evidence
    assert source.energy.spectrum_file == str(spectrum)


def test_runtime_aep8_evaluator_matches_known_l_shell_flux() -> None:
    pytest.importorskip("aep8")
    pytest.importorskip("astropy")
    evaluator = AEP8RuntimeFluxEvaluator()
    request = OrbitRadiationRequest(
        particle="proton",
        solar_period="min",
        l_shell=2.0,
        bb0=1.05,
        flux_mode="integral",
    )

    flux = evaluator.flux(model_name="AP8MIN", energy_mev=1.0, request=request)

    assert flux == pytest.approx(7215261.67, rel=2e-5)


def test_runtime_aep8_evaluator_accepts_geodetic_orbit_sample() -> None:
    pytest.importorskip("aep8")
    pytest.importorskip("astropy")
    evaluator = AEP8RuntimeFluxEvaluator()
    request = OrbitRadiationRequest(
        particle="proton",
        solar_period="min",
        geodetic_samples=[
            GeodeticOrbitSample(
                latitude_deg=0.0,
                longitude_deg=0.0,
                altitude_km=500.0,
                iso_time="2026-06-11T00:00:00",
            )
        ],
        flux_mode="integral",
    )

    flux = evaluator.flux(model_name="AP8MIN", energy_mev=10.0, request=request)

    assert flux >= 0.0


def test_runtime_aep8_evaluator_accepts_tle_orbit_request() -> None:
    pytest.importorskip("aep8")
    pytest.importorskip("astropy")
    pytest.importorskip("skyfield")
    evaluator = AEP8RuntimeFluxEvaluator()
    request = OrbitRadiationRequest(
        particle="proton",
        solar_period="min",
        tle_lines=(
            "1 25544U 98067A   26162.00000000  .00016717  00000+0  10270-3 0  9000",
            "2 25544  51.6400 120.0000 0006000  80.0000  40.0000 15.50000000 00001",
        ),
        start_time="2026-06-11T00:00:00Z",
        stop_time="2026-06-11T00:10:00Z",
        sample_count=3,
        flux_mode="integral",
    )

    flux = evaluator.flux(model_name="AP8MIN", energy_mev=10.0, request=request)

    assert flux >= 0.0
