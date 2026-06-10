#!/usr/bin/env python3
"""
Geant4 查询改写模块
- 将用户自然语言问题改写为适合向量检索的查询
- 提取 Geant4 关键词（类名、物理过程、几何等）
- 扩展同义词（如 "剂量" → "dose, energy deposit, scoring"）
- 多查询生成（一个用户问题 → 3个不同角度的检索查询）
"""

import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from knowledge_base.llm_client import call_llm

# ============================================================================
# Geant4 同义词和术语映射
# ============================================================================

GEANT4_SYNONYMS = {
    # 物理过程
    "electromagnetic": ["EM physics", "G4EmStandardPhysics", "Livermore", "Penelope", "electron gamma"],
    "hadronic": ["hadron physics", "QGSP", "FTFP", "BERT", "BIC", "Binary Cascade"],
    "radioactive decay": ["G4RadioactiveDecay", "nuclear decay", "G4Decay", "半衰期"],
    "optical photon": ["G4OpticalPhysics", "Cherenkov", "scintillation", "光子"],
    "dose": ["energy deposit", "scoring", "G4ScoringBox", "剂量", "absorbed dose"],
    "TID": ["total ionizing dose", "radiation damage", "single event effect", "SEE"],
    "LET": ["linear energy transfer", "stopping power", "energy loss", "Bethe-Bloch"],
    # 几何
    "geometry": ["G4VUserDetectorConstruction", "G4LogicalVolume", "G4VPhysicalVolume", "G4Box"],
    "material": ["G4Material", "G4NistManager", "density", "元素", "材料"],
    "volume": ["G4LogicalVolume", "G4PVPlacement", "G4PVParameterised", "母体体积"],
    "solid": ["G4Box", "G4Tubs", "G4Sphere", "G4Cons", "G4Trap", "G4Polycone"],
    # 用户动作
    "stepping": ["G4UserSteppingAction", "G4Step", "step length", "步长"],
    "event": ["G4UserEventAction", "G4Event", "primary vertex", "事件"],
    "run": ["G4UserRunAction", "G4Run", "beamOn", "运行"],
    "tracking": ["G4UserTrackingAction", "G4Track", "particle track", "粒子径迹"],
    "sensitive detector": ["G4VSensitiveDetector", "G4Hit", "G4Digi", "命中"],
    # 粒子
    "proton": ["G4Proton", "hadron therapy", "质子"],
    "electron": ["G4Electron", "bremsstrahlung", "ionization"],
    "gamma": ["G4Gamma", "photoelectric", "Compton", "pair production", "伽马"],
    "neutron": ["G4Neutron", "neutron scattering", "中子", "capture"],
    "alpha": ["G4Alpha", "helium-4", "重离子"],
    "muon": ["G4Muon", "cosmic ray", "介子"],
    # 分析
    "histogram": ["G4AnalysisManager", "ROOT", "HDF5", "CSV", "直方图"],
    "scoring": ["G4ScoringManager", "G4ScoringBox", "G4ScoringCylinder", "mesh"],
    "visualization": ["G4VisManager", "OpenGL", "Qt", "DAWN", "VRML", "可视化"],
    # 物理 List
    "FTFP_BERT": ["FTFP_BERTP", "hadronic physics", " Bertini cascade"],
    "QGSP_BIC": ["QGSP_BIC", "Binary Cascade", "proton neutron"],
    "Shielding": ["G4Shielding", "radiation shielding", "防护"],
    "QBBC": ["QBBC", "quark gluon string", "BIC cascade"],
    # 应用
    "medical": ["brachytherapy", "hadron therapy", "radiotherapy", "DICOM", "医学"],
    "detector": ["calorimeter", "tracker", "silicon detector", "探测器"],
    "shielding": ["辐射防护", "concrete", "lead", "iron", "bulk shielding"],
    "microelectronics": ["SEE", "SEL", "SEU", "SET", "single event", "TID"],
    "radiation damage": ["displacement damage", "NIEL", "TID", "radiation effect"],
}


# ============================================================================
# 查询改写提示词
# ============================================================================

REWRITE_SYSTEM = """你是 Geant4 蒙特卡洛粒子输运仿真领域的检索专家。
你擅长将用户的自然语言问题改写为精确的技术检索词。"""

REWRITE_PROMPT = """请将用户的查询改写为 3 个适合语义检索的英文查询。

改写要求：
1. 提取 Geant4 关键词（类名如 G4Box/G4Step/G4Run，物理过程如 electromagnetic/hadronic，用户动作如 SteppingAction/RunAction）
2. 扩展同义词（如 "剂量计算" → "dose scoring, energy deposit, G4ScoringBox"）
3. 从 3 个不同角度生成：
   - API/类名角度：涉及哪些 Geant4 类和方法
   - 物理/过程角度：涉及哪些物理过程和粒子
   - 应用场景角度：实际应用中的实现方式和示例
4. 每个查询占一行，不要编号，不要解释

用户查询：{query}

改写查询："""


def expand_synonyms(query: str) -> str:
    """基于同义词表扩展查询"""
    extra_terms = []
    query_lower = query.lower()
    for key, synonyms in GEANT4_SYNONYMS.items():
        if key.lower() in query_lower:
            extra_terms.extend(synonyms[:3])
    if extra_terms:
        extra_terms = list(dict.fromkeys(extra_terms))[:6]
        return query + " | related: " + ", ".join(extra_terms)
    return query


def rewrite_query(query: str) -> list[str]:
    """将用户查询改写为多个检索查询"""
    expanded = expand_synonyms(query)

    prompt = REWRITE_PROMPT.format(query=expanded)
    messages = [
        {"role": "system", "content": REWRITE_SYSTEM},
        {"role": "user", "content": prompt}
    ]

    try:
        response = call_llm(messages, temperature=0.5, max_tokens=512)
        queries = []
        for line in response.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            line = re.sub(r'^\d+[\.\)]\s*', '', line)
            line = line.strip('"\'""''')
            if line:
                queries.append(line)
    except Exception as e:
        print(f"  [WARN] 查询改写 LLM 失败，使用降级方案: {e}", file=sys.stderr)
        queries = _fallback_rewrite(expanded)

    result = [query]
    result.extend(queries[:3])
    return result


def _fallback_rewrite(query: str) -> list[str]:
    """LLM 不可用时的降级改写方案"""
    queries = []

    cn_to_en = {
        "如何": "how to", "仿真": "simulation", "模拟": "simulation",
        "剂量": "dose", "探测器": "detector", "几何": "geometry",
        "物理": "physics", "粒子": "particle", "辐射": "radiation",
        "电子": "electron", "质子": "proton", "光子": "photon gamma",
        "中子": "neutron", "步长": "stepping", "可视化": "visualization",
        "材料": "material", "敏感": "sensitive detector",
    }
    en_query = query
    for cn, en in cn_to_en.items():
        en_query = en_query.replace(cn, en)

    if en_query != query:
        queries.append(en_query)

    # 添加 Geant4 相关的变体
    if "Geant4" not in query and "geant" not in query.lower():
        queries.append(f"Geant4 {query}")

    return queries[:3]


def extract_keywords(query: str) -> list[str]:
    """从查询中提取 Geant4 领域关键词"""
    geant4_terms = [
        # Geant4 基础类
        "G4Run", "G4Event", "G4Step", "G4Track", "G4ParticleGun",
        "G4LogicalVolume", "G4VPhysicalVolume", "G4Material", "G4Box",
        "G4Tubs", "G4Sphere", "G4Cons", "G4Trap",
        # 用户动作
        "G4VUserDetectorConstruction", "G4VUserPhysicsList",
        "G4VUserPrimaryGeneratorAction", "G4UserRunAction",
        "G4UserEventAction", "G4UserSteppingAction", "G4UserTrackingAction",
        "G4VSensitiveDetector", "G4Hit", "G4Digi",
        # 物理过程
        "G4EmStandardPhysics", "G4EmLivermorePhysics", "G4EmPenelopePhysics",
        "G4OpticalPhysics", "G4RadioactiveDecay", "G4DecayPhysics",
        "G4HadronicProcessStore", "G4HadronElasticProcess",
        # 物理 List
        "FTFP_BERT", "QGSP_BIC", "QGSP_BERT", "QBBC", "Shielding",
        "G4EmStandardPhysics_option1", "G4EmStandardPhysics_option2",
        "G4EmStandardPhysics_option3", "G4EmStandardPhysics_option4",
        # 分析
        "G4AnalysisManager", "G4ScoringManager", "G4ScoringBox",
        "G4ScoringCylinder", "G4UIsession", "G4UImanager", "G4VisManager",
        # 粒子
        "proton", "electron", "gamma", "neutron", "alpha", "muon",
        "positron", "pion", "kaon", "deuteron", "triton",
        # 概念
        "electromagnetic", "hadronic", "dose", "scoring", "geometry",
        "material", "visualization", "sensitive detector", "physics list",
        "radioactive decay", "optical photon", "Cherenkov", "scintillation",
    ]

    found = []
    query_lower = query.lower()
    sorted_terms = sorted(geant4_terms, key=len, reverse=True)
    for term in sorted_terms:
        if term.lower() in query_lower:
            found.append(term)
            query_lower = query_lower.replace(term.lower(), "", 1)
    return found


if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_query = " ".join(sys.argv[1:])
    else:
        test_query = "如何用 Geant4 模拟硅中 TID 辐射产生的 LET 分布"

    print(f"原始查询: {test_query}")
    print(f"提取关键词: {extract_keywords(test_query)}")
    print(f"同义词扩展: {expand_synonyms(test_query)}")
    print()

    queries = rewrite_query(test_query)
    print(f"改写查询 ({len(queries)} 个):")
    for i, q in enumerate(queries):
        print(f"  [{i}] {q}")
