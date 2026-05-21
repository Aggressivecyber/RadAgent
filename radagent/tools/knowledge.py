"""Geant4 材料知识库 — 从 Geant4 11.3.2 NIST 数据库自动同步"""

from __future__ import annotations

import logging

logger = logging.getLogger("radagent.node.tools")


# 从 Geant4 11.3.2 NIST 数据库提取，共 309 种材料
# 直接传入 G4 名称即可，如 "G4_Al", "G4_WATER"
G4_MATERIALS: dict[str, float] = {
    "G4_1,2-DICHLOROBENZENE": 1.3048,
    "G4_1,2-DICHLOROETHANE": 1.2351,
    "G4_A-150_TISSUE": 1.127,
    "G4_ACETONE": 0.7899,
    "G4_ACETYLENE": 0.0010967,
    "G4_ADENINE": 1.35,
    "G4_ADIPOSE_TISSUE_ICRP": 0.95,
    "G4_AIR": 0.00120479,
    "G4_ALANINE": 1.42,
    "G4_ALUMINUM_OXIDE": 3.97,
    "G4_AMBER": 1.1,
    "G4_AMMONIA": 0.000826019,
    "G4_ANILINE": 1.0235,
    "G4_ANTHRACENE": 1.283,
    "G4_Ac": 10.07,
    "G4_Ag": 10.5,
    "G4_Al": 2.699,
    "G4_Am": 13.67,
    "G4_Ar": 0.00166201,
    "G4_As": 5.73,
    "G4_At": 9.32,
    "G4_Au": 19.32,
    "G4_B": 2.37,
    "G4_B-100_BONE": 1.45,
    "G4_BAKELITE": 1.25,
    "G4_BARIUM_FLUORIDE": 4.89,
    "G4_BARIUM_SULFATE": 4.5,
    "G4_BENZENE": 0.87865,
    "G4_BERYLLIUM_OXIDE": 3.01,
    "G4_BGO": 7.13,
    "G4_BLOOD_ICRP": 1.06,
    "G4_BONE_COMPACT_ICRU": 1.85,
    "G4_BONE_CORTICAL_ICRP": 1.92,
    "G4_BORON_CARBIDE": 2.52,
    "G4_BORON_OXIDE": 1.812,
    "G4_BRAIN_ICRP": 1.04,
    "G4_BRASS": 8.52,
    "G4_BRONZE": 8.82,
    "G4_BUTANE": 0.00249343,
    "G4_Ba": 3.5,
    "G4_Be": 1.848,
    "G4_Bi": 9.747,
    "G4_Bk": 14.0,
    "G4_Br": 0.0070721,
    "G4_C": 2.0,
    "G4_C-552": 1.76,
    "G4_CADMIUM_TELLURIDE": 6.2,
    "G4_CADMIUM_TUNGSTATE": 7.9,
    "G4_CALCIUM_CARBONATE": 2.8,
    "G4_CALCIUM_FLUORIDE": 3.18,
    "G4_CALCIUM_OXIDE": 3.3,
    "G4_CALCIUM_SULFATE": 2.96,
    "G4_CALCIUM_TUNGSTATE": 6.062,
    "G4_CARBON_DIOXIDE": 0.00184212,
    "G4_CARBON_TETRACHLORIDE": 1.594,
    "G4_CELLULOSE_BUTYRATE": 1.2,
    "G4_CELLULOSE_CELLOPHANE": 1.42,
    "G4_CELLULOSE_NITRATE": 1.49,
    "G4_CERIC_SULFATE": 1.03,
    "G4_CESIUM_FLUORIDE": 4.115,
    "G4_CESIUM_IODIDE": 4.51,
    "G4_CHLOROBENZENE": 1.1058,
    "G4_CHLOROFORM": 1.4832,
    "G4_CONCRETE": 2.3,
    "G4_CR39": 1.32,
    "G4_CYCLOHEXANE": 0.779,
    "G4_CYTOSINE": 1.3,
    "G4_Ca": 1.55,
    "G4_Cd": 8.65,
    "G4_Ce": 6.657,
    "G4_Cf": 10.0,
    "G4_Cl": 0.00299473,
    "G4_Cm": 13.51,
    "G4_Co": 8.9,
    "G4_Cr": 7.18,
    "G4_Cs": 1.873,
    "G4_Cu": 8.96,
    "G4_DACRON": 1.4,
    "G4_DEOXYRIBOSE": 1.5,
    "G4_DICHLORODIETHYL_ETHER": 1.2199,
    "G4_DIETHYL_ETHER": 0.71378,
    "G4_DIMETHYL_SULFOXIDE": 1.1014,
    "G4_DNA_ADENINE": 1.0,
    "G4_DNA_CYTOSINE": 1.0,
    "G4_DNA_DEOXYRIBOSE": 1.0,
    "G4_DNA_GUANINE": 1.0,
    "G4_DNA_PHOSPHATE": 1.0,
    "G4_DNA_THYMINE": 1.0,
    "G4_DNA_URACIL": 1.0,
    "G4_Dy": 8.55,
    "G4_ETHANE": 0.00125324,
    "G4_ETHYLENE": 0.00117497,
    "G4_ETHYL_ALCOHOL": 0.7893,
    "G4_ETHYL_CELLULOSE": 1.13,
    "G4_EYE_LENS_ICRP": 1.07,
    "G4_Er": 9.066,
    "G4_Eu": 5.243,
    "G4_F": 0.00158029,
    "G4_FERRIC_OXIDE": 5.2,
    "G4_FERROBORIDE": 7.15,
    "G4_FERROUS_OXIDE": 5.7,
    "G4_FERROUS_SULFATE": 1.024,
    "G4_FREON-12": 1.12,
    "G4_FREON-12B2": 1.8,
    "G4_FREON-13": 0.95,
    "G4_FREON-13B1": 1.5,
    "G4_FREON-13I1": 1.8,
    "G4_Fe": 7.874,
    "G4_Fr": 1.0,
    "G4_GADOLINIUM_OXYSULFIDE": 7.44,
    "G4_GALLIUM_ARSENIDE": 5.31,
    "G4_GEL_PHOTO_EMULSION": 1.2914,
    "G4_GLASS_LEAD": 6.22,
    "G4_GLASS_PLATE": 2.4,
    "G4_GLUTAMINE": 1.46,
    "G4_GLYCEROL": 1.2613,
    "G4_GRAPHITE": 2.21,
    "G4_GRAPHITE_POROUS": 1.7,
    "G4_GUANINE": 1.58,
    "G4_GYPSUM": 2.32,
    "G4_Ga": 5.904,
    "G4_Galactic": 1e-25,
    "G4_Gd": 7.9004,
    "G4_Ge": 5.323,
    "G4_H": 8.3748e-05,
    "G4_He": 0.000166322,
    "G4_Hf": 13.31,
    "G4_Hg": 13.546,
    "G4_Ho": 8.795,
    "G4_I": 4.93,
    "G4_In": 7.31,
    "G4_Ir": 22.42,
    "G4_K": 0.862,
    "G4_KAPTON": 1.42,
    "G4_KEVLAR": 1.44,
    "G4_Kr": 0.00347832,
    "G4_LANTHANUM_OXYBROMIDE": 6.28,
    "G4_LANTHANUM_OXYSULFIDE": 5.86,
    "G4_LEAD_OXIDE": 9.53,
    "G4_LITHIUM_AMIDE": 1.178,
    "G4_LITHIUM_CARBONATE": 2.11,
    "G4_LITHIUM_FLUORIDE": 2.635,
    "G4_LITHIUM_HYDRIDE": 0.82,
    "G4_LITHIUM_IODIDE": 3.494,
    "G4_LITHIUM_OXIDE": 2.013,
    "G4_LITHIUM_TETRABORATE": 2.44,
    "G4_LUCITE": 1.19,
    "G4_LUNG_ICRP": 1.04,
    "G4_La": 6.154,
    "G4_Li": 0.534,
    "G4_Lu": 9.84,
    "G4_M3_WAX": 1.05,
    "G4_MAGNESIUM_CARBONATE": 2.958,
    "G4_MAGNESIUM_FLUORIDE": 3.0,
    "G4_MAGNESIUM_OXIDE": 3.58,
    "G4_MAGNESIUM_TETRABORATE": 2.53,
    "G4_MERCURIC_IODIDE": 6.36,
    "G4_METHANE": 0.000667151,
    "G4_METHANOL": 0.7914,
    "G4_MIX_D_WAX": 0.99,
    "G4_MS20_TISSUE": 1.0,
    "G4_MUSCLE_SKELETAL_ICRP": 1.05,
    "G4_MUSCLE_STRIATED_ICRU": 1.04,
    "G4_MUSCLE_WITHOUT_SUCROSE": 1.07,
    "G4_MUSCLE_WITH_SUCROSE": 1.11,
    "G4_MYLAR": 1.4,
    "G4_Mg": 1.74,
    "G4_Mn": 7.44,
    "G4_Mo": 10.22,
    "G4_N": 0.0011652,
    "G4_N,N-DIMETHYL_FORMAMIDE": 0.9487,
    "G4_N-BUTYL_ALCOHOL": 0.8098,
    "G4_N-HEPTANE": 0.68376,
    "G4_N-HEXANE": 0.6603,
    "G4_N-PENTANE": 0.6262,
    "G4_N-PROPYL_ALCOHOL": 0.8035,
    "G4_NAPHTHALENE": 1.145,
    "G4_NEOPRENE": 1.23,
    "G4_NITROBENZENE": 1.19867,
    "G4_NITROUS_OXIDE": 0.00183094,
    "G4_NYLON-11_RILSAN": 1.425,
    "G4_NYLON-6-10": 1.14,
    "G4_NYLON-6-6": 1.14,
    "G4_NYLON-8062": 1.08,
    "G4_Na": 0.971,
    "G4_Nb": 8.57,
    "G4_Nd": 6.9,
    "G4_Ne": 0.000838505,
    "G4_Ni": 8.902,
    "G4_Np": 20.25,
    "G4_O": 0.00133151,
    "G4_OCTADECANOL": 0.812,
    "G4_OCTANE": 0.7026,
    "G4_Os": 22.57,
    "G4_P": 2.2,
    "G4_PARAFFIN": 0.93,
    "G4_PHOSPHORIC_ACID": 1.87,
    "G4_PHOTO_EMULSION": 3.815,
    "G4_PLASTIC_SC_VINYLTOLUENE": 1.032,
    "G4_PLEXIGLASS": 1.19,
    "G4_PLUTONIUM_DIOXIDE": 11.46,
    "G4_POLYACRYLONITRILE": 1.17,
    "G4_POLYCARBONATE": 1.2,
    "G4_POLYCHLOROSTYRENE": 1.3,
    "G4_POLYETHYLENE": 0.94,
    "G4_POLYOXYMETHYLENE": 1.425,
    "G4_POLYPROPYLENE": 0.9,
    "G4_POLYSTYRENE": 1.06,
    "G4_POLYTRIFLUOROCHLOROETHYLENE": 2.1,
    "G4_POLYVINYLIDENE_CHLORIDE": 1.7,
    "G4_POLYVINYLIDENE_FLUORIDE": 1.76,
    "G4_POLYVINYL_ACETATE": 1.19,
    "G4_POLYVINYL_ALCOHOL": 1.3,
    "G4_POLYVINYL_BUTYRAL": 1.12,
    "G4_POLYVINYL_CHLORIDE": 1.3,
    "G4_POLYVINYL_PYRROLIDONE": 1.25,
    "G4_POTASSIUM_IODIDE": 3.13,
    "G4_POTASSIUM_OXIDE": 2.32,
    "G4_PROPANE": 0.00187939,
    "G4_PYRIDINE": 0.9819,
    "G4_Pa": 15.37,
    "G4_Pb": 11.35,
    "G4_PbWO4": 8.28,
    "G4_Pd": 12.02,
    "G4_Pm": 7.22,
    "G4_Po": 9.32,
    "G4_Pr": 6.71,
    "G4_Pt": 21.45,
    "G4_Pu": 19.84,
    "G4_Pyrex_Glass": 2.23,
    "G4_RUBBER_BUTYL": 0.92,
    "G4_RUBBER_NATURAL": 0.92,
    "G4_RUBBER_NEOPRENE": 1.23,
    "G4_Ra": 5.0,
    "G4_Rb": 1.532,
    "G4_Re": 21.02,
    "G4_Rh": 12.41,
    "G4_Rn": 0.00900662,
    "G4_Ru": 12.41,
    "G4_S": 2.0,
    "G4_SILICON_DIOXIDE": 2.32,
    "G4_SILVER_BROMIDE": 6.473,
    "G4_SILVER_CHLORIDE": 5.56,
    "G4_SILVER_HALIDES": 6.47,
    "G4_SILVER_IODIDE": 6.01,
    "G4_SKIN_ICRP": 1.09,
    "G4_SODIUM_CARBONATE": 2.532,
    "G4_SODIUM_IODIDE": 3.667,
    "G4_SODIUM_MONOXIDE": 2.27,
    "G4_SODIUM_NITRATE": 2.261,
    "G4_STAINLESS-STEEL": 8.0,
    "G4_STILBENE": 0.9707,
    "G4_SUCROSE": 1.5805,
    "G4_Sb": 6.691,
    "G4_Sc": 2.989,
    "G4_Se": 4.5,
    "G4_Si": 2.33,
    "G4_Sm": 7.46,
    "G4_Sn": 7.31,
    "G4_Sr": 2.54,
    "G4_TEFLON": 2.2,
    "G4_TERPHENYL": 1.24,
    "G4_TESTIS_ICRP": 1.04,
    "G4_TETRACHLOROETHYLENE": 1.625,
    "G4_THALLIUM_CHLORIDE": 7.004,
    "G4_THYMINE": 1.48,
    "G4_TISSUE-METHANE": 0.00106409,
    "G4_TISSUE-PROPANE": 0.00182628,
    "G4_TISSUE_SOFT_ICRP": 1.03,
    "G4_TISSUE_SOFT_ICRU-4": 1.0,
    "G4_TITANIUM_DIOXIDE": 4.26,
    "G4_TOLUENE": 0.8669,
    "G4_TRICHLOROETHYLENE": 1.46,
    "G4_TRIETHYL_PHOSPHATE": 1.07,
    "G4_TUNGSTEN_HEXAFLUORIDE": 2.4,
    "G4_Ta": 16.654,
    "G4_Tb": 8.229,
    "G4_Tc": 11.5,
    "G4_Te": 6.24,
    "G4_Th": 11.72,
    "G4_Ti": 4.54,
    "G4_Tl": 11.72,
    "G4_Tm": 9.321,
    "G4_U": 18.95,
    "G4_URACIL": 1.32,
    "G4_URANIUM_DICARBIDE": 11.28,
    "G4_URANIUM_MONOCARBIDE": 13.63,
    "G4_URANIUM_OXIDE": 10.96,
    "G4_UREA": 1.323,
    "G4_V": 6.11,
    "G4_VALINE": 1.23,
    "G4_VITON": 1.8,
    "G4_W": 19.3,
    "G4_WATER": 1.0,
    "G4_WATER_VAPOR": 0.000756182,
    "G4_XYLENE": 0.87,
    "G4_Xe": 0.00548536,
    "G4_Y": 4.469,
    "G4_Yb": 6.73,
    "G4_Zn": 7.133,
    "G4_Zr": 6.506,
    "G4_lAr": 1.396,
    "G4_lBr": 3.1028,
    "G4_lH2": 0.0708,
    "G4_lKr": 2.418,
    "G4_lN2": 0.807,
    "G4_lO2": 1.141,
    "G4_lPROPANE": 0.43,
    "G4_lXe": 2.953,
}

# 中文/英文别名 → G4 材料名 (lowercase)
MATERIAL_ALIASES: dict[str, str] = {
    # 元素
    "氢": "G4_H", "hydrogen": "G4_H",
    "氦": "G4_He", "helium": "G4_He",
    "锂": "G4_Li", "lithium": "G4_Li",
    "铍": "G4_Be", "beryllium": "G4_Be",
    "硼": "G4_B", "boron": "G4_B",
    "碳": "G4_C", "carbon": "G4_C",
    "氮": "G4_N", "nitrogen": "G4_N",
    "氧": "G4_O", "oxygen": "G4_O",
    "氟": "G4_F", "fluorine": "G4_F",
    "氖": "G4_Ne", "neon": "G4_Ne",
    "钠": "G4_Na", "sodium": "G4_Na",
    "镁": "G4_Mg", "magnesium": "G4_Mg",
    "铝": "G4_Al", "aluminum": "G4_Al", "aluminium": "G4_Al", "al": "G4_Al", "铝合金": "G4_Al",
    "硅": "G4_Si", "silicon": "G4_Si", "si": "G4_Si",
    "磷": "G4_P", "phosphorus": "G4_P",
    "硫": "G4_S", "sulfur": "G4_S",
    "氯": "G4_Cl", "chlorine": "G4_Cl",
    "氩": "G4_Ar", "argon": "G4_Ar",
    "钾": "G4_K", "potassium": "G4_K",
    "钙": "G4_Ca", "calcium": "G4_Ca",
    "钪": "G4_Sc", "scandium": "G4_Sc",
    "钛": "G4_Ti", "titanium": "G4_Ti", "ti": "G4_Ti",
    "钒": "G4_V", "vanadium": "G4_V",
    "铬": "G4_Cr", "chromium": "G4_Cr",
    "锰": "G4_Mn", "manganese": "G4_Mn",
    "铁": "G4_Fe", "iron": "G4_Fe", "fe": "G4_Fe",
    "钴": "G4_Co", "cobalt": "G4_Co",
    "镍": "G4_Ni", "nickel": "G4_Ni",
    "铜": "G4_Cu", "copper": "G4_Cu", "cu": "G4_Cu",
    "锌": "G4_Zn", "zinc": "G4_Zn",
    "镓": "G4_Ga", "gallium": "G4_Ga",
    "锗": "G4_Ge", "germanium": "G4_Ge", "ge": "G4_Ge",
    "砷": "G4_As", "arsenic": "G4_As",
    "硒": "G4_Se", "selenium": "G4_Se",
    "溴": "G4_Br", "bromine": "G4_Br",
    "氪": "G4_Kr", "krypton": "G4_Kr",
    "铷": "G4_Rb", "rubidium": "G4_Rb",
    "锶": "G4_Sr", "strontium": "G4_Sr",
    "钇": "G4_Y", "yttrium": "G4_Y",
    "锆": "G4_Zr", "zirconium": "G4_Zr",
    "铌": "G4_Nb", "niobium": "G4_Nb",
    "钼": "G4_Mo", "molybdenum": "G4_Mo",
    "钌": "G4_Ru", "ruthenium": "G4_Ru",
    "铑": "G4_Rh", "rhodium": "G4_Rh",
    "钯": "G4_Pd", "palladium": "G4_Pd",
    "银": "G4_Ag", "silver": "G4_Ag",
    "镉": "G4_Cd", "cadmium": "G4_Cd",
    "铟": "G4_In", "indium": "G4_In",
    "锡": "G4_Sn", "tin": "G4_Sn",
    "锑": "G4_Sb", "antimony": "G4_Sb",
    "碲": "G4_Te", "tellurium": "G4_Te",
    "碘": "G4_I", "iodine": "G4_I",
    "氙": "G4_Xe", "xenon": "G4_Xe",
    "铯": "G4_Cs", "cesium": "G4_Cs",
    "钡": "G4_Ba", "barium": "G4_Ba",
    "镧": "G4_La", "lanthanum": "G4_La",
    "钽": "G4_Ta", "tantalum": "G4_Ta",
    "钨": "G4_W", "tungsten": "G4_W",
    "铼": "G4_Re", "rhenium": "G4_Re",
    "锇": "G4_Os", "osmium": "G4_Os",
    "铱": "G4_Ir", "iridium": "G4_Ir",
    "铂": "G4_Pt", "platinum": "G4_Pt",
    "金": "G4_Au", "gold": "G4_Au",
    "汞": "G4_Hg", "mercury": "G4_Hg",
    "铊": "G4_Tl", "thallium": "G4_Tl",
    "铅": "G4_Pb", "lead": "G4_Pb", "pb": "G4_Pb",
    "铋": "G4_Bi", "bismuth": "G4_Bi",
    "钍": "G4_Th", "thorium": "G4_Th",
    "铀": "G4_U", "uranium": "G4_U",
    "钚": "G4_Pu", "plutonium": "G4_Pu",
    # 化合物
    "水": "G4_WATER", "water": "G4_WATER",
    "水蒸气": "G4_WATER_VAPOR", "water_vapor": "G4_WATER_VAPOR",
    "空气": "G4_AIR", "air": "G4_AIR",
    "石墨": "G4_GRAPHITE", "graphite": "G4_GRAPHITE",
    "二氧化碳": "G4_CARBON_DIOXIDE", "co2": "G4_CARBON_DIOXIDE",
    "甲烷": "G4_METHANE", "methane": "G4_METHANE",
    "丙烷": "G4_PROPANE", "propane": "G4_PROPANE",
    "氨": "G4_AMMONIA", "ammonia": "G4_AMMONIA",
    # 氧化物
    "氧化铝": "G4_ALUMINUM_OXIDE", "al2o3": "G4_ALUMINUM_OXIDE", "alumina": "G4_ALUMINUM_OXIDE",
    "氧化铍": "G4_BERYLLIUM_OXIDE", "beo": "G4_BERYLLIUM_OXIDE",
    "氧化钙": "G4_CALCIUM_OXIDE", "cao": "G4_CALCIUM_OXIDE",
    "氧化铁": "G4_FERRIC_OXIDE", "fe2o3": "G4_FERRIC_OXIDE",
    "氧化镁": "G4_MAGNESIUM_OXIDE", "mgo": "G4_MAGNESIUM_OXIDE",
    "二氧化硅": "G4_SILICON_DIOXIDE", "sio2": "G4_SILICON_DIOXIDE", "silica": "G4_SILICON_DIOXIDE",
    "氧化钛": "G4_TITANIUM_DIOXIDE", "tio2": "G4_TITANIUM_DIOXIDE",
    "氧化铀": "G4_URANIUM_OXIDE", "uo2": "G4_URANIUM_OXIDE",
    "氧化铅": "G4_LEAD_OXIDE", "pbo": "G4_LEAD_OXIDE",
    "二氧化钚": "G4_PLUTONIUM_DIOXIDE", "puo2": "G4_PLUTONIUM_DIOXIDE",
    # 卤化物
    "氟化钡": "G4_BARIUM_FLUORIDE", "baf2": "G4_BARIUM_FLUORIDE",
    "氟化钙": "G4_CALCIUM_FLUORIDE", "caf2": "G4_CALCIUM_FLUORIDE",
    "氟化锂": "G4_LITHIUM_FLUORIDE", "lif": "G4_LITHIUM_FLUORIDE",
    "碘化铯": "G4_CESIUM_IODIDE", "csi": "G4_CESIUM_IODIDE",
    "碘化钠": "G4_SODIUM_IODIDE", "nai": "G4_SODIUM_IODIDE",
    "氯化银": "G4_SILVER_CHLORIDE", "agcl": "G4_SILVER_CHLORIDE",
    "溴化银": "G4_SILVER_BROMIDE", "agbr": "G4_SILVER_BROMIDE",
    "砷化镓": "G4_GALLIUM_ARSENIDE", "gaas": "G4_GALLIUM_ARSENIDE",
    # 合金
    "不锈钢": "G4_STAINLESS-STEEL", "stainless": "G4_STAINLESS-STEEL",
    "黄铜": "G4_BRASS", "brass": "G4_BRASS",
    "青铜": "G4_BRONZE", "bronze": "G4_BRONZE",
    "碳化硼": "G4_BORON_CARBIDE", "b4c": "G4_BORON_CARBIDE",
    "锗酸铋": "G4_BGO", "bgo": "G4_BGO",
    # 聚合物
    "聚乙烯": "G4_POLYETHYLENE", "polyethylene": "G4_POLYETHYLENE", "pe": "G4_POLYETHYLENE",
    "聚碳酸酯": "G4_POLYCARBONATE", "polycarbonate": "G4_POLYCARBONATE", "pc": "G4_POLYCARBONATE",
    "聚酰亚胺": "G4_KAPTON", "kapton": "G4_KAPTON", "pi": "G4_KAPTON",
    "聚苯乙烯": "G4_POLYSTYRENE", "polystyrene": "G4_POLYSTYRENE", "ps": "G4_POLYSTYRENE",
    "聚丙烯": "G4_POLYPROPYLENE", "polypropylene": "G4_POLYPROPYLENE", "pp": "G4_POLYPROPYLENE",
    "聚氯乙烯": "G4_POLYVINYL_CHLORIDE", "pvc": "G4_POLYVINYL_CHLORIDE",
    "聚四氟乙烯": "G4_TEFLON", "teflon": "G4_TEFLON", "ptfe": "G4_TEFLON",
    "聚甲醛": "G4_POLYOXYMETHYLENE", "pom": "G4_POLYOXYMETHYLENE",
    "涤纶": "G4_DACRON", "dacron": "G4_DACRON",
    "凯夫拉": "G4_KEVLAR", "kevlar": "G4_KEVLAR",
    "mylar": "G4_MYLAR",
    "有机玻璃": "G4_PLEXIGLASS", "plexiglass": "G4_PLEXIGLASS", "亚克力": "G4_PLEXIGLASS", "pmma": "G4_PLEXIGLASS",
    "胶木": "G4_BAKELITE", "bakelite": "G4_BAKELITE",
    "尼龙": "G4_NYLON-6-6", "nylon": "G4_NYLON-6-6", "nylon66": "G4_NYLON-6-6",
    "石蜡": "G4_PARAFFIN", "paraffin": "G4_PARAFFIN",
    "氟橡胶": "G4_VITON", "viton": "G4_VITON",
    # 液体
    "乙醇": "G4_ETHYL_ALCOHOL", "酒精": "G4_ETHYL_ALCOHOL", "ethyl_alcohol": "G4_ETHYL_ALCOHOL",
    "甲醇": "G4_METHANOL", "methanol": "G4_METHANOL",
    "丙酮": "G4_ACETONE", "acetone": "G4_ACETONE",
    "苯": "G4_BENZENE", "benzene": "G4_BENZENE",
    "甘油": "G4_GLYCEROL", "glycerol": "G4_GLYCEROL",
    "硫酸钡": "G4_BARIUM_SULFATE", "baso4": "G4_BARIUM_SULFATE",
    "碳酸钙": "G4_CALCIUM_CARBONATE", "caco3": "G4_CALCIUM_CARBONATE",
    # 玻璃/陶瓷
    "铅玻璃": "G4_GLASS_LEAD", "lead_glass": "G4_GLASS_LEAD",
    "玻璃": "G4_GLASS_PLATE", "glass": "G4_GLASS_PLATE",
    "硼硅玻璃": "G4_Pyrex_Glass", "pyrex": "G4_Pyrex_Glass", "派热克斯": "G4_Pyrex_Glass",
    "混凝土": "G4_CONCRETE", "concrete": "G4_CONCRETE",
    # 组织
    "组织": "G4_A-150_TISSUE", "tissue": "G4_A-150_TISSUE",
    "肌肉": "G4_MUSCLE_SKELETAL_ICRP", "muscle": "G4_MUSCLE_SKELETAL_ICRP",
    "骨骼": "G4_BONE_CORTICAL_ICRP", "bone": "G4_BONE_CORTICAL_ICRP",
    "皮肤": "G4_SKIN_ICRP", "skin": "G4_SKIN_ICRP",
    "脑": "G4_BRAIN_ICRP", "brain": "G4_BRAIN_ICRP",
    "肺": "G4_LUNG_ICRP", "lung": "G4_LUNG_ICRP",
    "血液": "G4_BLOOD_ICRP", "blood": "G4_BLOOD_ICRP",
    # 液态
    "液态氢": "G4_lH2", "liquid_hydrogen": "G4_lH2",
    "液态氮": "G4_lN2", "liquid_nitrogen": "G4_lN2",
    "液态氧": "G4_lO2", "liquid_oxygen": "G4_lO2",
    "液态氩": "G4_lAr", "liquid_argon": "G4_lAr",
    "液态氙": "G4_lXe", "liquid_xenon": "G4_lXe",
    # 闪烁体
    "蒽": "G4_ANTHRACENE", "anthracene": "G4_ANTHRACENE",
    "芪": "G4_STILBENE", "stilbene": "G4_STILBENE",
    # 自定义材料别名（不在 NIST 库中）
    "碳化硅": "G4_SiC", "sic": "G4_SiC", "silicon_carbide": "G4_SiC",
    "氮化镓": "G4_GaN", "gan": "G4_GaN", "gallium_nitride": "G4_GaN",
    "氯化钠": "G4_NaCl", "nacl": "G4_NaCl", "sodium_chloride": "G4_NaCl", "食盐": "G4_NaCl",
}


# ─── 自定义元素（同位素）— 不在 G4 NIST 自然丰度中 ───
# 用 G4Isotope + G4Element 定义特定同位素
CUSTOM_ELEMENTS: dict[str, dict] = {
    "D": {"description": "氘 Deuterium", "Z": 1, "A": 2, "symbol": "D"},
    "T": {"description": "氚 Tritium", "Z": 1, "A": 3, "symbol": "T"},
    "He3": {"description": "氦-3 Helium-3", "Z": 2, "A": 3, "symbol": "He"},
    "Li6": {"description": "锂-6 Lithium-6", "Z": 3, "A": 6, "symbol": "Li"},
    "Li7": {"description": "锂-7 Lithium-7", "Z": 3, "A": 7, "symbol": "Li"},
    "B10": {"description": "硼-10 Boron-10", "Z": 5, "A": 10, "symbol": "B"},
    "B11": {"description": "硼-11 Boron-11", "Z": 5, "A": 11, "symbol": "B"},
    "C13": {"description": "碳-13 Carbon-13", "Z": 6, "A": 13, "symbol": "C"},
    "N15": {"description": "氮-15 Nitrogen-15", "Z": 7, "A": 15, "symbol": "N"},
    "O18": {"description": "氧-18 Oxygen-18", "Z": 8, "A": 18, "symbol": "O"},
    "U235": {"description": "铀-235 Uranium-235", "Z": 92, "A": 235, "symbol": "U"},
    "U238": {"description": "铀-238 Uranium-238", "Z": 92, "A": 238, "symbol": "U"},
    "Pu239": {"description": "钚-239 Plutonium-239", "Z": 94, "A": 239, "symbol": "Pu"},
}

# 同位素别名
ELEMENT_ALIASES: dict[str, str] = {
    "氘": "D", "deuterium": "D", "d": "D",
    "氚": "T", "tritium": "T", "t": "T",
    "氦3": "He3", "he3": "He3", "helium3": "He3",
    "锂6": "Li6", "li6": "Li6", "lithium6": "Li6",
    "硼10": "B10", "b10": "B10", "boron10": "B10",
    "铀235": "U235", "u235": "U235",
    "钚239": "Pu239", "pu239": "Pu239",
}


# ─── 运行时自定义材料（由 define_custom 节点动态填充）───
# 初始为空，查不到 NIST 材料时由 LLM 生成定义并注册
CUSTOM_MATERIALS: dict[str, dict] = {}


PARTICLES: dict[str, str] = {
    "质子": "proton", "proton": "proton", "p": "proton",
    "伽马": "gamma", "gamma": "gamma", "光子": "gamma",
    "电子": "e-", "electron": "e-", "e-": "e-",
    "中子": "neutron", "neutron": "neutron",
    "阿尔法": "alpha", "alpha": "alpha", "α": "alpha",
    "氦离子": "alpha", "重离子": "heavyion", "铁离子": "Fe_ion",
    "pi+": "pi+", "pi-": "pi-",
    "mu-": "mu-", "mu+": "mu+",
    "deuteron": "deuteron", "氘核": "deuteron",
    "triton": "triton", "氚核": "triton",
}

# ─── 自定义粒子（离子）— 不在 G4 标准粒子表中 ───
CUSTOM_PARTICLES: dict[str, dict] = {
    "Fe_ion": {"description": "铁离子 Iron-56", "type": "ion", "Z": 26, "A": 56},
    "O_ion": {"description": "氧离子 Oxygen-16", "type": "ion", "Z": 8, "A": 16},
    "C_ion": {"description": "碳离子 Carbon-12", "type": "ion", "Z": 6, "A": 12},
    "Si_ion": {"description": "硅离子 Silicon-28", "type": "ion", "Z": 14, "A": 28},
    "Al_ion": {"description": "铝离子 Aluminum-27", "type": "ion", "Z": 13, "A": 27},
    "Ca_ion": {"description": "钙离子 Calcium-40", "type": "ion", "Z": 20, "A": 40},
    "Ti_ion": {"description": "钛离子 Titanium-48", "type": "ion", "Z": 22, "A": 48},
    "Cr_ion": {"description": "铬离子 Chromium-52", "type": "ion", "Z": 24, "A": 52},
    "Mn_ion": {"description": "锰离子 Manganese-55", "type": "ion", "Z": 25, "A": 55},
    "Co_ion": {"description": "钴离子 Cobalt-59", "type": "ion", "Z": 27, "A": 59},
    "Ni_ion": {"description": "镍离子 Nickel-58", "type": "ion", "Z": 28, "A": 58},
    "Cu_ion": {"description": "铜离子 Copper-63", "type": "ion", "Z": 29, "A": 63},
    "Zn_ion": {"description": "锌离子 Zinc-64", "type": "ion", "Z": 30, "A": 64},
}

# 粒子别名 → 自定义粒子名
PARTICLE_ALIASES: dict[str, str] = {
    "铁离子": "Fe_ion", "fe_ion": "Fe_ion", "iron_ion": "Fe_ion",
    "氧离子": "O_ion", "o_ion": "O_ion", "oxygen_ion": "O_ion",
    "碳离子": "C_ion", "c_ion": "C_ion", "carbon_ion": "C_ion",
    "硅离子": "Si_ion", "si_ion": "Si_ion", "silicon_ion": "Si_ion",
    "铝离子": "Al_ion", "al_ion": "Al_ion", "aluminum_ion": "Al_ion",
    "钙离子": "Ca_ion", "ca_ion": "Ca_ion", "calcium_ion": "Ca_ion",
    "钛离子": "Ti_ion", "ti_ion": "Ti_ion", "titanium_ion": "Ti_ion",
    "铬离子": "Cr_ion", "cr_ion": "Cr_ion", "chromium_ion": "Cr_ion",
    "锰离子": "Mn_ion", "mn_ion": "Mn_ion", "manganese_ion": "Mn_ion",
    "钴离子": "Co_ion", "co_ion": "Co_ion", "cobalt_ion": "Co_ion",
    "镍离子": "Ni_ion", "ni_ion": "Ni_ion", "nickel_ion": "Ni_ion",
    "铜离子": "Cu_ion", "cu_ion": "Cu_ion", "copper_ion": "Cu_ion",
    "锌离子": "Zn_ion", "zn_ion": "Zn_ion", "zinc_ion": "Zn_ion",
}


def lookup_material(name: str) -> tuple[str, float]:
    """查找材料: G4_XXX 直接匹配 → 别名匹配 → 自定义材料 → 模糊匹配 → 报错"""
    key = name.strip()

    # 1. 直接 G4_ 前缀匹配
    if key in G4_MATERIALS:
        logger.debug("材料查找(G4): %s → %.4f g/cm3", key, G4_MATERIALS[key])
        return key, G4_MATERIALS[key]

    # 2. 自定义材料
    if key in CUSTOM_MATERIALS:
        info = CUSTOM_MATERIALS[key]
        logger.debug("材料查找(自定义): %s → %.4f g/cm3", key, info["density_g_cm3"])
        return key, info["density_g_cm3"]

    # 3. 别名匹配
    lower = key.lower().replace(" ", "")
    g4_name = MATERIAL_ALIASES.get(lower)
    if g4_name:
        if g4_name in G4_MATERIALS:
            logger.debug("材料查找(别名): %s → %s", name, g4_name)
            return g4_name, G4_MATERIALS[g4_name]
        if g4_name in CUSTOM_MATERIALS:
            logger.debug("材料查找(别名→自定义): %s → %s", name, g4_name)
            return g4_name, CUSTOM_MATERIALS[g4_name]["density_g_cm3"]

    # 4. 模糊匹配 (别名中包含)
    for alias, g4name in MATERIAL_ALIASES.items():
        if lower in alias:
            if g4name in G4_MATERIALS:
                logger.debug("材料查找(模糊): %s → %s", name, g4name)
                return g4name, G4_MATERIALS[g4name]

    raise ValueError(
        f"未知材料: '{name}'。请使用 G4_NIST 材料名或添加到 CUSTOM_MATERIALS。"
        f"可用材料: {len(G4_MATERIALS)} NIST + {len(CUSTOM_MATERIALS)} 自定义"
    )


def is_custom_material(g4_name: str) -> bool:
    """判断是否为自定义材料（需要生成 C++ 定义代码）"""
    return g4_name in CUSTOM_MATERIALS


def _generate_isotope_cpp(z: int, symbol: str, a: int) -> list[str]:
    """为同位素生成 G4Isotope + G4Element C++ 代码"""
    var = f"{symbol}{a}"
    return [
        f'  auto iso_{var} = new G4Isotope("{var}", {z}, {a});',
        f'  auto ele_{var} = new G4Element("{symbol}-{a}", "{symbol}", 1);',
        f'  ele_{var}->AddIsotope(iso_{var}, 100.*perCent);',
    ]


def generate_custom_material_cpp(g4_name: str) -> str | None:
    """为自定义材料生成 C++ 定义代码片段，插入 DetectorConstruction。
    elements 格式:
      (Z, symbol, count)       → nist->FindOrBuildElement(Z)
      (Z, symbol, count, A)    → G4Isotope + G4Element (自定义同位素)
    """
    if g4_name not in CUSTOM_MATERIALS:
        return None

    mat = CUSTOM_MATERIALS[g4_name]
    lines = [f'  // {mat["description"]}']
    density_val = mat["density_g_cm3"]
    lines.append(f'  G4double {g4_name}_dens = {density_val} * g/cm3;')

    if mat["type"] == "compound":
        elems = mat["elements"]

        # 先生成同位素定义（需在材料定义之前）
        for elem in elems:
            if len(elem) >= 4:
                z, symbol, _, a = elem[:4]
                lines.extend(_generate_isotope_cpp(z, symbol, a))

        # 材料定义
        lines.append(f'  auto {g4_name}_mat = new G4Material("{g4_name}", {g4_name}_dens, {len(elems)});')

        # 添加元素
        for elem in elems:
            count = elem[2]
            if len(elem) >= 4:
                z, symbol, _, a = elem[:4]
                lines.append(f'  {g4_name}_mat->AddElement(ele_{symbol}{a}, {count});')
            else:
                z = elem[0]
                lines.append(f'  {g4_name}_mat->AddElement(nist->FindOrBuildElement({z}), {count});')

    return "\n".join(lines)


def lookup_particle(name: str) -> str:
    """查找粒子的 Geant4 名称"""
    key = name.strip().lower()
    result = PARTICLES.get(key)
    if result:
        return result
    # 别名 → 自定义粒子
    alias = PARTICLE_ALIASES.get(key)
    if alias:
        return alias
    for k, v in PARTICLES.items():
        if key in k.lower():
            return v
    raise ValueError(f"未知粒子: '{name}'。请在 PARTICLES 或 CUSTOM_PARTICLES 中添加")


def try_lookup_material(name: str) -> tuple[str, float] | tuple[None, None]:
    """软查找材料: 未找到返回 (None, None) 而非抛异常"""
    try:
        return lookup_material(name)
    except ValueError:
        return None, None


def try_lookup_particle(name: str) -> str | None:
    """软查找粒子: 未找到返回 None 而非抛异常"""
    try:
        return lookup_particle(name)
    except ValueError:
        return None


def register_custom_material(g4_name: str, definition: dict) -> None:
    """运行时注册自定义材料"""
    CUSTOM_MATERIALS[g4_name] = definition
    logger.info("注册自定义材料: %s (ρ=%.4f)", g4_name, definition["density_g_cm3"])


def register_custom_particle(g4_name: str, definition: dict) -> None:
    """运行时注册自定义粒子（离子）"""
    CUSTOM_PARTICLES[g4_name] = definition
    logger.info("注册自定义粒子: %s (Z=%d, A=%d)", g4_name, definition["Z"], definition["A"])


def register_custom_element(name: str, definition: dict) -> None:
    """运行时注册自定义元素（同位素）"""
    CUSTOM_ELEMENTS[name] = definition
    logger.info("注册自定义元素: %s (Z=%d, A=%d)", name, definition["Z"], definition["A"])


def lookup_custom_element(name: str) -> dict | None:
    """查找自定义元素（同位素），返回定义 dict 或 None"""
    key = name.strip()
    if key in CUSTOM_ELEMENTS:
        return CUSTOM_ELEMENTS[key]
    alias = ELEMENT_ALIASES.get(key.lower())
    if alias and alias in CUSTOM_ELEMENTS:
        return CUSTOM_ELEMENTS[alias]
    return None


def is_custom_element(name: str) -> bool:
    """判断是否为自定义元素（同位素）"""
    return lookup_custom_element(name) is not None


def is_custom_particle(name: str) -> bool:
    """判断是否为自定义粒子（离子，需要 G4IonTable 代码）"""
    return name in CUSTOM_PARTICLES


def generate_custom_particle_cpp(g4_name: str) -> str | None:
    """为自定义粒子（离子）生成 C++ 代码片段，用于 PrimaryGeneratorAction"""
    if g4_name not in CUSTOM_PARTICLES:
        return None
    p = CUSTOM_PARTICLES[g4_name]
    return (
        f'  // {p["description"]}\n'
        f'  auto ionTable = G4IonTable::GetInstance();\n'
        f'  fParticleGun->SetParticleDefinition(ionTable->GetIon({p["Z"]}, {p["A"]}));'
    )


def recommend_physics(particle: str, energy_MeV: float) -> str:
    """根据粒子类型和能量推荐 Geant4 物理列表"""
    return _do_recommend_physics(particle, energy_MeV)


def _do_recommend_physics(particle: str, energy_MeV: float) -> str:
    if particle == "proton":
        return "QGSP_BIC" if energy_MeV < 200 else "QGSP_BERT"
    if particle in ("e-", "gamma"):
        return "QBBC"
    if particle == "alpha":
        return "QGSP_BIC"
    if particle == "neutron":
        return "QGSP_BERT"
    return "QBBC"
