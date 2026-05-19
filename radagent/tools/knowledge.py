MATERIALS = {
    "聚酰亚胺": {"geant4": "G4_KAPTON", "density": 1.42},
    "kapton": {"geant4": "G4_KAPTON", "density": 1.42},
    "pi": {"geant4": "G4_KAPTON", "density": 1.42},
    "水": {"geant4": "G4_WATER", "density": 1.0},
    "water": {"geant4": "G4_WATER", "density": 1.0},
    "硅": {"geant4": "G4_Si", "density": 2.33},
    "silicon": {"geant4": "G4_Si", "density": 2.33},
    "si": {"geant4": "G4_Si", "density": 2.33},
    "铝": {"geant4": "G4_Al", "density": 2.70},
    "aluminum": {"geant4": "G4_Al", "density": 2.70},
    "al": {"geant4": "G4_Al", "density": 2.70},
    "铜": {"geant4": "G4_Cu", "density": 8.96},
    "copper": {"geant4": "G4_Cu", "density": 8.96},
    "cu": {"geant4": "G4_Cu", "density": 8.96},
    "铁": {"geant4": "G4_Fe", "density": 7.87},
    "iron": {"geant4": "G4_Fe", "density": 7.87},
    "fe": {"geant4": "G4_Fe", "density": 7.87},
    "聚乙烯": {"geant4": "G4_POLYETHYLENE", "density": 0.94},
    "polyethylene": {"geant4": "G4_POLYETHYLENE", "density": 0.94},
    "pe": {"geant4": "G4_POLYETHYLENE", "density": 0.94},
    "聚碳酸酯": {"geant4": "G4_POLYCARBONATE", "density": 1.20},
    "polycarbonate": {"geant4": "G4_POLYCARBONATE", "density": 1.20},
    "pc": {"geant4": "G4_POLYCARBONATE", "density": 1.20},
    "二氧化硅": {"geant4": "G4_SILICON_DIOXIDE", "density": 2.20},
    "sio2": {"geant4": "G4_SILICON_DIOXIDE", "density": 2.20},
    "碳": {"geant4": "G4_C", "density": 2.27},
    "carbon": {"geant4": "G4_C", "density": 2.27},
    "石墨": {"geant4": "G4_GRAPHITE", "density": 2.23},
    "graphite": {"geant4": "G4_GRAPHITE", "density": 2.23},
    "碳化硼": {"geant4": "G4_B4C", "density": 2.52},
    "b4c": {"geant4": "G4_B4C", "density": 2.52},
    "铅": {"geant4": "G4_Pb", "density": 11.35},
    "lead": {"geant4": "G4_Pb", "density": 11.35},
    "pb": {"geant4": "G4_Pb", "density": 11.35},
    "空气": {"geant4": "G4_AIR", "density": 0.001214},
    "air": {"geant4": "G4_AIR", "density": 0.001214},
    "组织": {"geant4": "G4_A-150_TISSUE", "density": 0.97},
    "tissue": {"geant4": "G4_A-150_TISSUE", "density": 0.97},
}

PARTICLES = {
    "质子": "proton",
    "proton": "proton",
    "伽马": "gamma",
    "gamma": "gamma",
    "光子": "gamma",
    "电子": "e-",
    "electron": "e-",
    "e-": "e-",
    "中子": "neutron",
    "neutron": "neutron",
    "阿尔法": "alpha",
    "alpha": "alpha",
    "α": "alpha",
    "氦离子": "alpha",
}


def lookup_material(name: str) -> tuple[str, float]:
    key = name.strip().lower()
    info = MATERIALS.get(key, MATERIALS.get(key.replace(" ", ""), None))
    if info:
        return info["geant4"], info["density"]
    for k, v in MATERIALS.items():
        if key in k.lower():
            return v["geant4"], v["density"]
    return "G4_AIR", 0.001214


def lookup_particle(name: str) -> str:
    key = name.strip().lower()
    result = PARTICLES.get(key)
    if result:
        return result
    for k, v in PARTICLES.items():
        if key in k.lower():
            return v
    return "proton"


def recommend_physics(particle: str, energy_MeV: float) -> str:
    if particle == "proton":
        return "QGSP_BIC" if energy_MeV < 200 else "QGSP_BERT"
    if particle in ("e-", "gamma"):
        return "QBBC"
    if particle == "alpha":
        return "QGSP_BIC"
    if particle == "neutron":
        return "QGSP_BERT"
    return "QBBC"
