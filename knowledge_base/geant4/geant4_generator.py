#!/usr/bin/env python3
"""
Geant4 C++ 代码生成模块
- 检索代码示例后，结合用户需求生成 Geant4 仿真项目代码
- 输出完整的 C++ 源文件，带中文注释
- 支持 main()、DetectorConstruction、PhysicsList、PrimaryGenerator 等
"""

import json
import sys
import time
import urllib.request
import urllib.error

from geant4_rag_mcp import search_documents, keyword_search_func, get_document
from query_rewrite import rewrite_query

# 智谱 LLM API 配置
LLM_API_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
LLM_API_KEY = "f5dc034a22df47ac8cf98c37710e0bc6.crvx5afiTuITC247"
LLM_MODEL = "glm-5-turbo"


def call_llm(messages: list[dict], temperature: float = 0.4, max_tokens: int = 8192) -> str:
    """调用智谱 LLM API"""
    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }, ensure_ascii=False).encode('utf-8')

    req = urllib.request.Request(
        LLM_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}"
        }
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                return result["choices"][0]["message"]["content"]
        except (urllib.error.URLError, KeyError, json.JSONDecodeError, IndexError) as e:
            if attempt < max_retries - 1:
                print(f"  [RETRY] LLM 调用失败 (attempt {attempt+1}): {e}", file=sys.stderr)
                time.sleep(2)
            else:
                raise RuntimeError(f"LLM 调用失败: {e}") from e


# ============================================================================
# 代码生成系统提示词
# ============================================================================

CODE_GEN_SYSTEM = """你是 Geant4 蒙特卡洛粒子输运仿真 C++ 代码生成专家。

你能根据用户需求和参考代码示例，生成完整的 Geant4 仿真项目代码。

Geant4 仿真项目的核心组件：
1. main() — 初始化 RunManager，设置用户动作类
2. DetectorConstruction (G4VUserDetectorConstruction) — 定义几何和材料
3. PhysicsList (G4VModularPhysicsList) — 选择物理过程
4. PrimaryGeneratorAction (G4VUserPrimaryGeneratorAction) — 定义粒子源
5. RunAction (G4UserRunAction) — 开始/结束运行时操作
6. EventAction (G4UserEventAction) — 事件级操作
7. SteppingAction (G4UserSteppingAction) — 每步操作（能量沉积记录等）
8. SensitiveDetector (G4VSensitiveDetector) — 敏感探测器命中收集

生成规则：
1. 输出完整、可编译的 C++ 代码，包含所有必要的 #include
2. 添加清晰的中文注释，解释每个关键步骤
3. 参考提供的代码示例的架构和风格
4. 合理设置默认物理参数（世界体积大小、粒子能量等）
5. 使用现代 Geant4 API（11.x 兼容）
6. 包含 CMakeLists.txt 构建配置

输出格式：
- 按文件分别输出，每个文件在 ```cpp 代码块中
- 代码前说明文件用途
- 代码后说明如何编译和运行
- 如果只需要部分代码（如某个 Action 类），只输出相关文件"""


# ============================================================================
# 检索相关代码示例
# ============================================================================

def retrieve_code_examples(requirements: str, top_k: int = 8) -> list[dict]:
    """检索与需求相关的代码示例"""
    queries = rewrite_query(requirements)
    all_results = []
    seen_ids = set()

    for q in queries:
        results = search_documents(q, top_k=3)
        for r in results:
            if isinstance(r, dict) and "doc_id" in r and r["doc_id"] not in seen_ids:
                seen_ids.add(r["doc_id"])
                meta = r.get("metadata", {})
                if isinstance(meta, dict) and meta.get("type") == "example":
                    all_results.insert(0, r)
                else:
                    all_results.append(r)

    # 关键词补充
    geant4_keywords = ["G4Box", "G4Run", "G4Step", "G4Material", "PhysicsList",
                       "DetectorConstruction", "PrimaryGenerator", "SensitiveDetector",
                       "SteppingAction", "G4ScoringBox", "G4EmStandardPhysics",
                       "electromagnetic", "hadronic", "dose"]
    req_lower = requirements.lower()
    for sk in geant4_keywords:
        if sk.lower() in req_lower:
            kw_results = keyword_search_func(sk, top_k=3)
            for r in kw_results:
                if isinstance(r, dict) and "doc_id" in r and r["doc_id"] not in seen_ids:
                    seen_ids.add(r["doc_id"])
                    all_results.append(r)

    full_examples = []
    for r in all_results[:5]:
        doc = get_document(r["doc_id"])
        if "error" not in doc:
            full_examples.append(doc)

    return full_examples


# ============================================================================
# 代码生成
# ============================================================================

def generate_geant4_code(requirements: str) -> str:
    """根据需求生成 Geant4 仿真代码"""
    examples = retrieve_code_examples(requirements)

    examples_text = ""
    if examples:
        examples_text = "以下是从知识库中检索到的参考代码示例：\n\n"
        for i, ex in enumerate(examples):
            content = ex.get("content", "")
            title = ex.get("title", "Unknown")
            if len(content) > 3000:
                content = content[:3000] + "\n// ... (代码已截断)"
            examples_text += f"### 示例 {i+1}: {title}\n```\n{content}\n```\n\n"
    else:
        examples_text = "未检索到相关代码示例，请基于通用 Geant4 知识生成。\n"

    user_prompt = f"""用户需求：{requirements}

{examples_text}

请根据以上需求和参考示例，生成完整的 Geant4 仿真项目代码。
要求：
1. 输出可直接编译运行的完整 C++ 代码
2. 每个关键步骤加中文注释（C++ 注释用 // ）
3. 合理设置物理参数默认值
4. 包含必要的头文件
5. 提供对应的 CMakeLists.txt
6. 如涉及特定物理过程，使用合适的 Physics List

请生成 Geant4 代码："""

    messages = [
        {"role": "system", "content": CODE_GEN_SYSTEM},
        {"role": "user", "content": user_prompt}
    ]

    try:
        response = call_llm(messages, temperature=0.3, max_tokens=8192)
        return response
    except RuntimeError as e:
        return f"代码生成失败: {e}"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_req = " ".join(sys.argv[1:])
    else:
        test_req = "proton therapy dose calculation in water phantom"

    print(f"需求: {test_req}")
    print("=" * 60)

    code = generate_geant4_code(test_req)

    print(code)
