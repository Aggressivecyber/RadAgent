"""Generate diverse G4ModelIR variants from job_cbb4f07a's IR for generality testing.

Each variant is a fully self-consistent IR (components/materials/sources/physics/
scoring/SDs aligned) stressing a different codegen aspect. Written to
/tmp/variant_irs/<name>.json.
"""
from __future__ import annotations
import copy, json, os
from pathlib import Path

BASE = "/home/rylan/RadAgent/simulation_workspace/jobs/job_cbb4f07a__20260612_072455/03_model_ir/g4_model_ir.json"
OUT = Path("/tmp/variant_irs"); OUT.mkdir(parents=True, exist_ok=True)

_base = json.loads(Path(BASE).read_text())


def _clone() -> dict:
    return copy.deepcopy(_base)


def _nist(name: str, density: float) -> dict:
    return {
        "material_id": name,
        "name": f"{name} (NIST)",
        "classification": "nist",
        "nist_name": name,
        "composition": None,
        "density_g_cm3": density,
        "state": "solid",
        "temperature_kelvin": None,
        "source_evidence": [f"nist:{name}"],
        "open_issues": [],
    }


def _box(cid: str, display: str, dx: float, dy: float, dz: float,
         mat: str, mother: str | None, pos: list[float], sensitive: bool = True) -> dict:
    return {
        "component_id": cid,
        "display_name": display,
        "component_type": "world" if mother is None else "detector",
        "geometry_type": "box",
        "dimensions": {"dx": dx, "dy": dy, "dz": dz},
        "material_id": mat,
        "placement": {"position": pos, "rotation": [0.0, 0.0, 0.0]},
        "mother_volume": mother,
        "sensitive": sensitive,
        "roles": ["edep_region", "dose_scoring_region"] if sensitive else [],
        "color": None,
        "source_evidence": [f"variant:{cid}"],
        "open_issues": [],
        "requires_confirmation": False,
        "confirmed_by_user": False,
        "confirmation_source": None,
    }


def _sd(sd_id: str, name: str, comp: str, coll: str) -> dict:
    return {
        "sd_id": sd_id, "name": name,
        "linked_component_ids": [comp], "scoring_ids": [],
        "collection_name": coll,
        "hit_fields": [
            {"name": "event_id", "dtype": "int", "unit": None},
            {"name": "track_id", "dtype": "int", "unit": None},
            {"name": "edep_MeV", "dtype": "double", "unit": "MeV"},
            {"name": "pos_x_mm", "dtype": "double", "unit": "mm"},
        ],
        "source_evidence": [f"variant:{sd_id}"], "open_issues": [],
    }


def _region_scoring(comp: str) -> dict:
    return {
        "scoring_id": f"{comp}_edep", "scoring_type": "region",
        "quantities": ["edep_MeV", "dose_Gy"], "voxel_grid": None,
        "region_scores": [{"region_component_id": comp, "quantity": "edep_MeV"}],
        "output_format": "csv", "source_evidence": [f"variant:{comp}"], "open_issues": [],
    }


def _set_source(ir: dict, particle: str, energy_mev: float, pos_z: float) -> None:
    s = ir["sources"][0]
    s["particle_type"] = particle
    s["energy"] = {"value": energy_mev, "unit": "MeV", "distribution": "mono",
                   "sigma": None, "spectrum_file": None}
    s["beam"]["position"] = [0.0, 0.0, pos_z]
    s["beam"]["direction"] = [0.0, 0.0, 1.0]
    # Keep the IR internally consistent so the physics_quality_reviewer does
    # not flag a stale source_evidence (it cross-checks the declared source
    # against the embedded evidence strings).
    s["source_evidence"] = [f"variant:{particle}@{energy_mev}MeV"]
    for k in ("selection_reasoning", "evidence"):
        if isinstance(s.get(k), str):
            s[k] = f"variant source: {particle} at {energy_mev} MeV"


def _finalize(ir: dict, name: str, components: list[dict], materials: list[dict]) -> dict:
    ir["components"] = components
    ir["materials"] = materials
    sens = [c["component_id"] for c in components if c.get("sensitive")]
    ir["sensitive_detectors"] = [
        _sd(f"{c}_sd", f"{c.capitalize()}SdSensitiveDetector", c, f"{c}_Hits")
        for c in sens
    ]
    ir["scoring"] = [_region_scoring(c) for c in sens]
    ir["model_ir_id"] = f"mir_variant_{name}"
    ir["job_id"] = f"variant_{name}"
    return ir


# ── Variant 1: multi-layer detector (Si + water + lead), proton 50 MeV ────────
def variant_multi_layer() -> dict:
    ir = _clone()
    comps = [
        _box("world_volume", "World", 60000, 60000, 60000, "Air", None, [0, 0, 0], sensitive=False),
        _box("silicon_layer", "Si Layer", 10000, 10000, 1000, "Silicon", "world_volume", [0, 0, -1000]),
        _box("water_layer", "Water Layer", 10000, 10000, 2000, "Water", "world_volume", [0, 0, 500]),
        _box("lead_layer", "Pb Layer", 10000, 10000, 500, "Lead", "world_volume", [0, 0, 2000]),
    ]
    mats = [
        _nist("G4_AIR", 0.001225), _nist("G4_Si", 2.329),
        _nist("G4_WATER", 1.0), _nist("G4_Pb", 11.35),
    ]
    # rename material ids to match component material_id fields
    mid = {"Air": "G4_AIR", "Silicon": "G4_Si", "Water": "G4_WATER", "Lead": "G4_Pb"}
    for c in comps:
        c["material_id"] = mid[c["material_id"]]
    _set_source(ir, "proton", 50.0, -5000.0)
    ir["physics"]["physics_list"] = "QGSP_BIC"
    ir["physics"]["selection_reasoning"] = "Multi-layer proton shower — QGSP_BIC for hadronic + EM"
    return _finalize(ir, "multi_layer", comps, mats)


# ── Variant 2: gamma source 5 MeV into silicon ────────────────────────────────
def variant_gamma() -> dict:
    ir = _clone()
    comps = [
        _box("world_volume", "World", 50000, 50000, 50000, "G4_AIR", None, [0, 0, 0], sensitive=False),
        _box("silicon_slab", "Si Slab", 10000, 10000, 1000, "G4_Si", "world_volume", [0, 0, 0]),
    ]
    mats = [_nist("G4_AIR", 0.001225), _nist("G4_Si", 2.329)]
    _set_source(ir, "gamma", 5.0, -2000.0)
    ir["physics"]["physics_list"] = "FTFP_BERT"
    ir["physics"]["selection_reasoning"] = "Gamma EM shower — FTFP_BERT EM + low-rate hadronic"
    return _finalize(ir, "gamma", comps, mats)


# ── Variant 3: cylindrical silicon target (non-box solid) ─────────────────────
def variant_cylinder() -> dict:
    ir = _clone()
    cyl = {
        "component_id": "silicon_target", "display_name": "Si Cylinder",
        "component_type": "detector", "geometry_type": "tubs",
        "dimensions": {"rmin": 0.0, "rmax": 5000.0, "dz": 500.0, "sphi": 0.0, "dphi": 360.0},
        "material_id": "G4_Si",
        "placement": {"position": [0, 0, 0], "rotation": [0.0, 0.0, 0.0]},
        "mother_volume": "world_volume", "sensitive": True,
        "roles": ["edep_region", "dose_scoring_region"], "color": None,
        "source_evidence": ["variant:cylinder"], "open_issues": [],
        "requires_confirmation": False, "confirmed_by_user": False, "confirmation_source": None,
    }
    world = _box("world_volume", "World", 50000, 50000, 50000, "G4_AIR", None, [0, 0, 0], sensitive=False)
    comps = [world, cyl]
    mats = [_nist("G4_AIR", 0.001225), _nist("G4_Si", 2.329)]
    _set_source(ir, "proton", 10.0, -2000.0)
    ir["physics"]["physics_list"] = "FTFP_BERT"
    ir["physics"]["selection_reasoning"] = "Proton into cylindrical target"
    return _finalize(ir, "cylinder", comps, mats)


def _tubs(cid: str, display: str, rmin: float, rmax: float, dz: float,
          mat: str, mother: str | None, pos: list[float], sensitive: bool = True) -> dict:
    """G4Tubs component. dz is the half-length in um (Geant4 G4Tubs convention)."""
    return {
        "component_id": cid, "display_name": display,
        "component_type": "world" if mother is None else "detector",
        "geometry_type": "tubs",
        "dimensions": {"rmin": rmin, "rmax": rmax, "dz": dz, "sphi": 0.0, "dphi": 360.0},
        "material_id": mat,
        "placement": {"position": pos, "rotation": [0.0, 0.0, 0.0]},
        "mother_volume": mother, "sensitive": sensitive,
        "roles": ["edep_region", "dose_scoring_region"] if sensitive else [],
        "color": None, "source_evidence": [f"variant:{cid}"], "open_issues": [],
        "requires_confirmation": False, "confirmed_by_user": False, "confirmation_source": None,
    }


# ── Variant 4: HPGe coaxial gamma spectrometer ────────────────────────────────
# Realistic high-purity germanium detector: Al endcap + Ge crystal + central
# bore, all nested G4Tubs; Co-60 1.33 MeV gamma. Stresses nested cylindrical
# volumes (3 levels deep) + gamma + multiple sensitive regions.
def variant_hpge() -> dict:
    ir = _clone()
    comps = [
        _box("world_volume", "World", 200000, 200000, 200000, "G4_AIR", None, [0, 0, 0], sensitive=False),
        _tubs("alu_endcap", "Al Endcap", 0, 40000, 50000, "G4_Al", "world_volume", [0, 0, 0], sensitive=False),
        _tubs("ge_crystal", "Ge Crystal", 0, 33000, 40000, "G4_Ge", "alu_endcap", [0, 0, 0]),
        _tubs("bore", "Central Bore", 0, 5000, 38000, "G4_AIR", "ge_crystal", [0, 0, 0], sensitive=False),
    ]
    mats = [_nist("G4_AIR", 0.001225), _nist("G4_Al", 2.699),
            _nist("G4_Ge", 5.323)]
    _set_source(ir, "gamma", 1.33, -60000.0)
    ir["sources"][0]["events"] = 1000
    ir["physics"]["physics_list"] = "FTFP_BERT"
    ir["physics"]["selection_reasoning"] = "HPGe gamma spectroscopy — EM + Compton/photopeak"
    return _finalize(ir, "hpge", comps, mats)


# ── Variant 5: sampling EM calorimeter (Pb absorber + plastic scintillator) ───
# 3 sampling layers of lead absorber + plastic scintillator, 50 MeV electron
# shower. Stresses multi-layer shower physics + many sensitive volumes.
def variant_calo() -> dict:
    ir = _clone()
    # stack along z: pb, sc, pb, sc, pb, sc — each 2mm thick (dz full=2000um)
    layers = []
    z = -9000
    for i in range(1, 4):
        layers.append(_box(f"pb_abs{i}", f"Pb Absorber {i}", 30000, 30000, 2000, "G4_Pb", "world_volume", [0, 0, z], sensitive=False))
        z += 2000
        layers.append(_box(f"sc_tile{i}", f"Scintillator {i}", 30000, 30000, 2000, "G4_POLYSTYRENE", "world_volume", [0, 0, z]))
        z += 2000
    comps = [_box("world_volume", "World", 200000, 200000, 200000, "G4_AIR", None, [0, 0, 0], sensitive=False)] + layers
    mats = [_nist("G4_AIR", 0.001225), _nist("G4_Pb", 11.35),
            _nist("G4_POLYSTYRENE", 1.032)]
    _set_source(ir, "e-", 50.0, -15000.0)
    ir["sources"][0]["events"] = 1000
    ir["physics"]["physics_list"] = "FTFP_BERT"
    ir["physics"]["selection_reasoning"] = "EM calorimeter shower — FTFP_BERT EM"
    return _finalize(ir, "calorimeter", comps, mats)


# ── Variant 6: silicon pixel tracker (5 thin layers) ──────────────────────────
# 5 thin (0.3mm) silicon pixel planes, 1 GeV proton. Stresses many thin
# sensitive volumes + tracking-style scoring.
def variant_tracker() -> dict:
    ir = _clone()
    layers = []
    for i, z in enumerate([-8000, -4000, 0, 4000, 8000]):
        layers.append(_box(f"si_layer{i+1}", f"Si Layer {i+1}", 20000, 20000, 300, "G4_Si", "world_volume", [0, 0, z]))
    comps = [_box("world_volume", "World", 200000, 200000, 200000, "G4_AIR", None, [0, 0, 0], sensitive=False)] + layers
    mats = [_nist("G4_AIR", 0.001225), _nist("G4_Si", 2.329)]
    _set_source(ir, "proton", 1000.0, -15000.0)
    ir["sources"][0]["events"] = 1000
    ir["physics"]["physics_list"] = "QGSP_BIC"
    ir["physics"]["selection_reasoning"] = "Charged-particle tracking — QGSP_BIC"
    return _finalize(ir, "tracker", comps, mats)


for fn, name in [(variant_multi_layer, "multi_layer"),
                 (variant_gamma, "gamma"),
                 (variant_cylinder, "cylinder"),
                 (variant_hpge, "hpge"),
                 (variant_calo, "calorimeter"),
                 (variant_tracker, "tracker")]:
    ir = fn()
    p = OUT / f"{name}.json"
    p.write_text(json.dumps(ir, indent=2, ensure_ascii=False))
    print(f"wrote {p}  (components={[c['component_id'] for c in ir['components']]}, "
          f"particle={ir['sources'][0]['particle_type']}, "
          f"physics={ir['physics']['physics_list']})")
