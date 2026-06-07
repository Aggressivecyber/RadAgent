# RadAgent — Geant4 Complex Modeling Agent

基于 LangGraph 主图 + 8 子图架构的 Geant4 复杂建模智能体系统。

## 架构概览

```
用户自然语言输入
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│                    Main Graph (调度器)                     │
│   仅负责调度，不包含领域逻辑。所有 I/O 通过 JSON 文件路径。  │
│   TCAD/SPICE scope 被 HARD BLOCK — 仅路由到 report。       │
└──────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────┐   ┌──────────────┐   ┌──────────────┐
│ Context │──▶│ Task Planning│──▶│ G4 Modeling  │
│ Subgraph│   │ Subgraph     │   │ Subgraph     │
└─────────┘   └──────────────┘   └──────────────┘
                                        │
                                        ▼
┌─────────┐   ┌──────────────┐   ┌──────────────┐
│ Artifact│◀──│ Gate Valid.  │◀──│ Patch        │◀──┐
│ Subgraph│   │ Subgraph     │   │ Subgraph     │   │
└────┬────┘   └──────────────┘   └──────────────┘   │
     │              ▲                        ▲        │
     ▼              │                        │        │
┌─────────┐         │               ┌──────────────┐  │
│ Report  │         └───────────────│ G4 Codegen   │──┘
│ Subgraph│   (failure routing)     │ Subgraph     │
└─────────┘                         └──────────────┘
```

### 8 个子图

| 子图 | 职责 | 内部节点数 |
|------|------|-----------|
| **Context** | RAG + Web 上下文收集，证据评分 | 6 |
| **Task Planning** | 解析用户需求，生成 task spec | 3 |
| **G4 Modeling** | Model IR 构建（15 节点管线） | 15 |
| **G4 Codegen** | 模块化 C++ 代码生成 | 11 |
| **Patch** | Patch 格式审查 + 权限校验 + 应用 | 3 |
| **Gate Validation** | 19 道门禁检查（Gate 0-11 + G4-A~G4-G） | 4 |
| **Artifact** | GitHub-reviewable 产物收集 | 3 |
| **Report** | 最终报告生成 | 1 |

### 设计原则

1. **主图仅调度** — 不处理几何、C++ 代码、门禁细节
2. **子图隔离** — 每个子图有独立的输入/输出 schema，可独立测试
3. **JSON 文件 I/O** — 子图间通信只通过结构化 JSON 文件路径
4. **路径化状态** — 主状态只持有文件路径，不持有内联数据
5. **禁止未批准简化** — 复杂模型需用户明确批准才可简化
6. **TCAD/SPICE 硬阻断** — 非 geant4 scope 被路由到 report_subgraph，不进入建模/代码生成

### 当前范围

- ✅ **支持**: Geant4 复杂真实建模
- 🚫 **保留（未实现）**: TCAD Sentaurus、ngspice
- TCAD/SPICE scope 会被 `report_subgraph` 阻断，报告标注 "reserved for later MVP"
- 复杂建模使用 Geant4 Model IR（9+ 组件，5+ 材料，4 种 scoring）
- `latest` artifact 必须是真实复杂样例，不允许 stub

## 门禁系统

### 基础门禁 (Gate 0-11)

| Gate | 名称 | 说明 |
|------|------|------|
| 0 | Context Sufficiency | RAG + Web 上下文充分性 |
| 1 | Task Spec Schema | 任务规格完整性 |
| 2 | Model IR Schema | Model IR 完整性 |
| 3 | Patch Format | Patch 格式正确性 |
| 4 | File Permissions | 文件权限策略合规 |
| 5 | Static Analysis | Geant4 代码结构检查（src/include/CMakeLists.txt） |
| 6 | Build/Parse | 编译或语法检查 |
| 7 | Unit Tests | 核心功能单元测试（验收模式不可自动通过） |
| 8 | Data Contract | g4_output_package 格式校验 |
| 9 | Smoke Test | 小规模仿真验证（验收模式不可自动通过） |
| 10 | Benchmark Regression | 基准测试对比 |
| 11 | Physics Sanity | NaN/Inf/负值检查 |

### G4 建模门禁 (G4-A ~ G4-G)

| Gate | 名称 | 说明 |
|------|------|------|
| G4-A | Model Completeness | 必需组件/材料/源/物理列表完整 |
| G4-B | **No Unapproved Simplification** | 检测缺失组件、层合并、简化 — 复杂模型只有 world+silicon 必须失败 |
| G4-C | Geometry Interface | 母子体积接口一致性 |
| G4-D | Overlap Policy | 无体积重叠 |
| G4-E | Evidence Traceability | 每个参数有证据来源 |
| G4-F | Code Module Boundary | 代码模块边界清晰 |
| G4-G | No Magic Number | 无硬编码物理常数 |

### Gate 输出格式

每个 gate 输出详细结构（禁止只写 OK）：

```json
{
  "gate_id": "G4-B",
  "name": "No Unapproved Simplification",
  "status": "pass | fail | skipped",
  "checked_items": [{"item": "housing preserved", "result": "pass"}],
  "passed_items": ["housing preserved", "pcb preserved"],
  "failed_items": [],
  "warnings": [],
  "evidence": ["component_ids: ..."],
  "file_paths": [],
  "message": "..."
}
```

## Review Artifacts

每次成功运行后，产物自动收集到 `review_artifacts/g4_complex_model/latest/`。

**当前 artifact 是基于真实复杂探测器模型（非 stub）**：

```
latest/
├── README.md
├── artifact_manifest.json
├── review_report.json                 # is_stub: false, run_type: dev
└── output/
    ├── g4_model_ir.json               # 9 组件, 5 材料, 4 scoring
    ├── gate_results.json              # 19 gates with detailed checked_items
    ├── component_specs_summary.json
    ├── no_simplification_report.json
    ├── geometry_interface_report.json
    ├── evidence_traceability_report.json
    ├── output_manager_contract.json   # g4_output_package 契约
    ├── model_review_report.md
    ├── code_module_plan.json
    ├── construction_ledger.json
    └── proposed_patch_summary.json
```

### 真实复杂模型样例组件

| 组件 | 材料 | 角色 |
|------|------|------|
| world | G4_AIR | 根体积 |
| housing | G4_Al | 铝外壳/屏蔽 |
| pcb | FR4 (custom) | PCB 载板 |
| sensor_stack | G4_AIR | 传感器组件容器 |
| top_electrode | G4_Al | 顶部铝电极 |
| oxide_layer | SiO2 (custom) | 1 μm SiO2 氧化层 |
| silicon_bulk | G4_Si | 硅衬底 |
| sensitive_region | G4_Si | 灵敏活性区 |
| bottom_electrode | G4_Al | 底部铝电极 |

## OutputManager 契约 (g4_output_package)

OutputManager 代码生成器从 Model IR scoring specs 读取输出规格，生成：

| 文件 | 内容 |
|------|------|
| g4_summary.json | 运行元数据（事件数、束流、物理列表） |
| edep_3d.csv | 能量沉积 |
| dose_3d.csv | 剂量分布 |
| event_table.csv | 事件级数据 |
| provenance.json | Model IR 来源 |
| run_log.txt | 运行日志 |

**禁止 OutputManager 自行创造输出字段 — 所有字段来自 scoring spec。**

## 项目结构

```
RadAgent/
├── agent_core/
│   ├── graph/
│   │   ├── main_graph.py          # 主图构建（调度器）
│   │   ├── main_state.py          # 主状态定义（路径化）
│   │   ├── main_routes.py         # 条件路由（TCAD/SPICE 硬阻断）
│   │   └── subgraphs/             # 8 个子图构建器
│   ├── context/                   # Context Subgraph
│   ├── planning/                  # Task Planning Subgraph
│   ├── g4_modeling/               # G4 Modeling Subgraph
│   │   ├── schemas/               # G4ModelIR, ComponentSpec, MaterialSpec 等
│   │   ├── validators/            # NoSimplification, EvidenceTraceability 等
│   │   └── codegen/               # OutputManager 等代码生成器
│   ├── g4_codegen/                # G4 Codegen Subgraph
│   │   ├── nodes/                 # code_module_planner, integration_assembler 等
│   │   └── validators/            # code_module_boundary, no_magic_number, cmake_structure
│   ├── patching/                  # Patch Subgraph
│   ├── gates/
│   │   ├── base_gates.py          # Gate 0-11
│   │   ├── g4_modeling_gates.py   # G4-A 到 G4-G
│   │   ├── gate_runner.py         # 统一运行和汇总
│   │   └── failure_classifier.py  # 失败归因和回路
│   ├── artifacts/                 # Artifact Subgraph
│   ├── reports/                   # Report Subgraph
│   ├── config/                    # 配置（workspace 路径）
│   └── main.py                    # 入口点
├── review_artifacts/              # GitHub-reviewable 产物
├── tests/
│   ├── unit/                      # 单元测试（262+）
│   ├── e2e/                       # 端到端测试（4+）
│   └── unit/g4_modeling/          # G4 建模专项测试（81+）
└── scripts/
    └── generate_complex_model_artifact.py  # artifact 生成脚本
```

## 快速开始

```bash
# 安装依赖
pip install -e ".[dev]"

# 配置环境变量
cp .env.example .env

# 运行全部测试（275 个）
pytest tests/

# 仅运行单元测试
pytest tests/unit/

# 仅运行 E2E 测试
pytest tests/e2e/

# 运行 Agent
python -m agent_core.main "模拟 10 MeV 质子束垂直入射硅探测器"
```

## 测试覆盖

| 测试文件 | 覆盖范围 |
|----------|---------|
| test_main_graph_subgraph_routing.py | 主图条件路由 |
| test_task_planning_scope_guard.py | TCAD/SPICE scope 硬阻断（11 测试） |
| test_gate_subgraph.py | 基础门禁 + G4 建模门禁 |
| test_g4_modeling_subgraph.py | G4 建模子图编译和节点 |
| test_g4_codegen_subgraph.py | G4 代码生成子图 |
| test_no_simplification_gate_hard.py | G4-B 简化检测（5 硬测试） |
| test_output_manager_contract.py | OutputManager g4_output_package 契约 |
| test_required_g4_code_structure.py | Geant4 代码结构 Gate 5 合规 |
| test_architecture_invariants.py | 架构不变性（29 项检查） |
| g4_modeling/ | G4 建模专项测试（81+） |

## 许可证

MIT
