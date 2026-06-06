# Radiation Simulation Agent (RadAgent)

基于 LangGraph 的自主代码生成型辐照联合仿真智能体系统。

## MVP-1 状态

**🚧 候选版 / 未验收** — Geant4 自主代码生成 + 12 道门禁已实现。待 `mvp1_acceptance` 模式完整运行后更新状态。

## 概述

RadAgent 是一个工程化 Agent 平台，能够：

1. 理解用户辐照仿真需求（自然语言输入）
2. 根据需求调用对应 RAG 知识库（Geant4 / TCAD / SPICE）
3. RAG 不足时通过 Web Search 补足上下文
4. 自主生成仿真代码、命令文件、网表或数据转换脚本
5. 通过严格门禁（12 道门）检查代码正确性
6. 管理 Geant4 → TCAD → SPICE 之间的数据传递
7. 生成可复现仿真报告

## 知识获取策略（RAG 优先 + Web 补足）

RadAgent 遵循严格的上下文充分性原则：

1. **RAG 优先**：所有仿真知识优先从 RAG 知识库获取
   - Geant4 RAG — Geant4 物理列表、探测器构建、敏感探测器等
   - TCAD RAG — Sentaurus 工具链、器件仿真、辐照效应等（MVP-2+）
   - SPICE RAG — ngspice 仿真、BSIM-CMG 模型等（MVP-2+）

2. **Web Search 补足**：当 RAG 评分 ≥ 0.60 但 < 0.90 时，允许 Web Search 补充
   - 所有 Web 结果必须标注 `[WEB SUPPLEMENT — verify independently]`
   - 后端：DuckDuckGo HTML（默认，无需 API key）或 Exa（可选）
   - Web 放行门槛：≥ 2 个有效 URL + ≥ 1 个官方来源 + title/snippet 命中关键词

3. **无充分上下文时终止**：当 RAG 评分 < 0.60 且 Web 也无法补足时，**管线终止**
   - **禁止依赖模型内置知识继续写代码**
   - 终止原因写入报告

### Gate 0: RAG + Web Context Sufficiency

| 场景 | RAG 评分 | Web 补充 | 结果 |
|------|---------|---------|------|
| RAG 充分 | ≥ 0.90 | — | `allow_rag` → pass |
| RAG 不足 + Web 补足 | ≥ 0.60 | ≥ 2 URL, ≥ 1 官方源, 关键词命中 | `allow_with_web_supplement` → warning (pass with disclosure) |
| RAG + Web 都不足 | < 0.60 | — | `block_no_context` → 终止 |

## 架构

```
用户输入 → LangGraph 状态调度 → Task Spec → Simulation IR
    → RAG 路由 → 统一 RAG 检索 (retrieve_required_context) → RAG 充分性评分
      ├─ allow_rag              → 代码生成
      ├─ needs_web → Web Search → 组合评分 → 代码生成 / 终止
      └─ block_no_context       → 报告（终止）
    → [MVP-1 Scope Guard] → 仅允许 Geant4 代码生成
    → Agent 自主代码生成 → Patch → 12 道门禁检查
    → 小规模仿真 → 数据契约校验 → 正式仿真 → 报告
```

### MVP-1 Scope Guard

MVP-1 只允许 `simulation_scope == ["geant4"]`。如果 task_spec 包含 TCAD/SPICE：
- RAG 检索和报告生成 **允许**
- `write_code_patch` **阻断** — 不会为 TCAD/SPICE 生成代码
- 报告明确标注 "TCAD/SPICE reserved for later MVPs"

## MVP 进度

| MVP | 描述 | 状态 |
|-----|------|------|
| MVP-1 | Geant4 自主代码生成 + 门禁 | 🚧 候选版 / 未验收 |
| MVP-2 | Geant4 输出标准数据包 + 数据契约 | 📋 规划中 |
| MVP-3 | Geant4 → TCAD 映射器 | 📋 规划中 |
| MVP-4 | TCAD 自主命令生成 + 门禁 | 📋 规划中 |
| MVP-5 | TCAD → SPICE 映射器 | 📋 规划中 |
| MVP-6 | SPICE 自主网表生成 + 门禁 | 📋 规划中 |
| MVP-7 | G4—TCAD—SPICE 全链路联合仿真 | 📋 规划中 |
| MVP-8 | 自动报告 + 基准回归 + 参数扫描 | 📋 规划中 |

## 快速开始

```bash
# 安装依赖
pip install -e ".[dev]"

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API key（DeepSeek、可选 Exa）

# 运行测试（214 个单元测试）
pytest tests/

# 运行 Agent（示例）
python -m agent_core.main "模拟 10 MeV 质子垂直入射 300 微米硅片"
```

## 项目结构

```
RadAgent/
├── agent_core/           # 核心 Agent 代码
│   ├── graph/            # LangGraph 图定义（状态、路由、构建器）
│   ├── nodes/            # LangGraph 节点（RAG 检索、代码生成、门禁等）
│   ├── tools/            # Agent 工具（RAG、Web Search、Patch、Geant4 Runner）
│   ├── schemas/          # 数据 Schema（Pydantic 模型）
│   ├── validators/       # 验证器（静态检查、数据契约、物理一致性）
│   ├── config/           # 配置（工作空间路径）
│   └── policies/         # 策略文件（文件权限、门禁、RAG）
├── knowledge_base/       # RAG 知识库目录
├── simulation_workspace/ # 仿真工作空间（运行时生成，不入 Git）
├── benchmark_suite/      # 基准测试套件
└── tests/                # 测试（单元测试）
```

## 门禁系统

共 12 道门禁，所有代码必须逐门通过。MVP-1 验收模式下 Gate 6/8/9/11 不可跳过。

| Gate | 名称 | 检查内容 |
|------|------|----------|
| 0 | **RAG + Web Context Sufficiency** | RAG 优先；RAG 不足 Web 补充；RAG+Web 都不足终止 |
| 1 | Task Spec Schema | 任务规格是否完整 |
| 2 | Simulation IR Schema | 仿真中间表示是否完整 |
| 3 | Patch 格式 | Patch 格式是否正确 |
| 4 | 文件权限 | 是否遵守文件权限策略 |
| 5 | 静态检查 | 语法、格式、类型 |
| 6 | 编译/解析 | CMake 编译或 SPICE 语法检查 |
| 7 | 单元测试 | 核心功能单元测试 |
| 8 | 数据契约 | 数据包格式校验 |
| 9 | 小规模仿真 | Smoke test（详见下方） |
| 10 | 基准回归 | 基准测试对比 |
| 11 | 物理一致性 | NaN/Inf/负值检查 |

### Gate 9 验证项

1. 5 个必需文件存在：`g4_summary.json`, `edep_3d.csv`, `dose_3d.csv`, `event_table.csv`, `provenance.json`
2. `event_table.csv` ≥ 1 行数据
3. `provenance.json` 的 `simulation_id` == 当前 `job_id`
4. `g4_summary.json` 的 `simulation_id` == 当前 `job_id`
5. **所有 5 个输出文件**必须在 `patch_applied_at` 时间戳之后生成（防止旧文件冒充本轮输出）

## 数据契约

所有跨模块数据传递必须通过标准化数据契约：

- `g4_output_contract` — Geant4 输出包（5 个 FileInfo 条目，含 checksum）
- `g4_to_tcad_contract` — Geant4 → TCAD 映射
- `tcad_input_contract` — TCAD 输入包
- `tcad_output_contract` — TCAD 输出包
- `tcad_to_spice_contract` — TCAD → SPICE 映射
- `spice_output_contract` — SPICE 输出包

## 测试覆盖

| 测试文件 | 覆盖范围 |
|----------|---------|
| test_schemas.py | Pydantic 模型验证 |
| test_validators.py | Schema/patch/physics 验证器 |
| test_patch_discipline.py | Patch 纪律约束 |
| test_rag_router.py | RAG 路由逻辑 |
| test_workspace_paths.py | 工作空间路径解析 |
| test_score_rag_sufficiency.py | RAG 充分性评分（含 0.76 伪造消除验证） |
| test_web_search_tool.py | Web Search 后端检测和 DDG 解析 |
| test_combined_context_sufficiency.py | RAG×Web 组合决策 |
| test_gate_validation.py | Gate 0/6/9 验证 |
| test_routes.py | Graph 路由目标 |
| test_gate0_rag_web_sufficiency.py | Gate 0 三态决策 |
| test_web_fallback_policy.py | Web fallback 策略和 disclosure |
| test_gate11_physics_sanity.py | Gate 11 NaN/Inf/负值检测 |
| test_g4_output_contract_parser_consistency.py | G4 output contract 一致性 |
| test_geant4_runner_output_env.py | Geant4Runner 环境变量注入 |
| test_acceptance_mode_no_skip.py | MVP-1 验收模式不可跳过 |
| test_no_legacy_names.py | 代码库无遗留名称（含大写环境变量扫描） |
| test_no_tracked_job_artifacts.py | 无 Git 跟踪的作业输出 |

## 许可证

MIT
