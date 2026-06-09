"""Material module agent — generates MaterialRegistry.hh/cc."""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import ModuleAgentResult

MATERIAL_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 材料模块编码 Agent。

你只负责 MaterialRegistry.hh 和 MaterialRegistry.cc。

职责：
1. 使用 G4NistManager 获取 NIST 材料
2. 定义自定义材料（如需要）
3. 提供按名称查找材料的接口
4. 材料名称映射

严格要求：
1. 只生成 MaterialRegistry.hh 和 MaterialRegistry.cc
2. 不得生成 geometry、source、physics 等其他模块代码
3. 使用 G4SystemOfUnits.hh 中的单位
4. 不得输出 Markdown fence
5. 不得出现 TODO/NotImplemented/stub
6. 必须支持自定义材料定义，至少提供 AddCustomMaterial 或 RegisterCustomMaterial 接口，
   能把调用方提供/创建的 G4Material* 注册进内部名称映射
7. Initialize 必须同时注册 IR 中的 NIST 材料和自定义材料名称；找不到材料时要显式处理，
   不得静默 skip，也不得写 "for now"、"should handle" 这类占位注释
8. GetMaterial 不得只返回 nullptr；找不到材料时应先尝试 G4NistManager::FindOrBuildMaterial，
   仍失败时抛出异常或返回明确失败路径
9. 不要同时声明 GetMaterial(const G4String&) 和 GetMaterial(const std::string&)；
   字符串字面量会产生 overload 二义性。优先只保留 G4String 版本。
10. Initialize 或 DefineAllMaterials 必须真实调用 FindOrBuildMaterial / AddCustomMaterial /
    RegisterCustomMaterial 完成材料注册；不要写“注册由其它函数完成”的占位注释
11. 不要在任何代码或注释中出现 placeholder、dummy、stub、TODO、NotImplemented
12. 必须提供 static MaterialRegistry* GetInstance()，供 geometry/main 等模块共享同一个
    registry；GetInstance() 返回函数内 static MaterialRegistry 的地址。
13. G4Exception severity 必须使用 Geant4 存在的枚举，例如 FatalException 或
    FatalErrorInArgument；不要写 FatalErrorInArguments。
14. G4Exception 的第 4 个参数不能是 std::string/G4String 拼接表达式。
    如果错误消息需要包含材料名，使用 G4ExceptionDescription：
    G4ExceptionDescription desc;
    desc << "Material not found: " << name;
    G4Exception("MaterialRegistry::GetMaterial", "mat05", FatalException, desc);
    或传入一个稳定的 const char*。不要写
    G4Exception(..., "Material not found: " + name)。
15. 输出 JSON 格式
"""


async def run_material_agent(
    module_context: dict[str, Any],
) -> ModuleAgentResult:
    """Run material module agent."""
    result = await run_module_agent(
        module_name="material",
        module_context=module_context,
        system_prompt=MATERIAL_SYSTEM_PROMPT,
    )
    return result
