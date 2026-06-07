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

### 设计原则

1. **主图仅调度** — 不处理几何、C++ 代码、门禁细节
2. **子图隔离** — 每个子图有独立的输入/输出 schema，可独立测试
3. **JSON 文件 I/O** — 子图间通信只通过结构化 JSON 文件路径
4. **路径化状态** — 主状态只持有文件路径，不持有内联数据
5. **禁止未批准简化** — 复杂模型需用户明确批准才可简化

## 子图说明

| 子图 | 职责 | 内部节点数 |
|------|------|-----------|
| Context | RAG + Web 上下文收集，证据评分 | 6 |
| Task Planning | 解析用户需求，生成 task spec | 3 |
| G4 Modeling | Model IR 构建（15 节点管线） | 15 |
| G4 Codegen | 模块化 C++ 代码生成 | 11 |
| Patch | Patch 格式审查 + 权限校验 + 应用 | 3 |
| Gate Validation | 19 道门禁检查（Gate 0-11 + G4-A~G4-G） | 4 |
| Artifact | GitHub-reviewable 产物收集 | 3 |
| Report | 最终报告生成 | 1 |

## 门禁系统

### 基础门禁 (Gate 0-11)

| Gate | 名称 | 说明 |
|------|------|------|
| 0 | Context Sufficiency | RAG + Web 上下文充分性 |
| 1 | Task Spec Schema | 任务规格完整性 |
| 2 | Model IR Schema | Model IR 完整性 |
| 3 | Patch Format | Patch 格式正确性 |
| 4 | File Permissions | 文件权限策略合规 |
| 5 | Static Analysis | 语法/格式/类型检查 |
| 6 | Build/Parse | 编译或语法检查 |
| 7 | Unit Tests | 核心功能单元测试 |
| 8 | Data Contract | 数据包格式校验 |
| 9 | Smoke Test | 小规模仿真验证 |
| 10 | Benchmark Regression | 基准测试对比 |
| 11 | Physics Sanity | NaN/Inf/负值检查 |

**重要**: Gate 7-11 在验收模式下不可自动通过。

### G4 建模门禁 (G4-A ~ G4-G)

| Gate | 名称 | 说明 |
|------|------|------|
| G4-A | Model Completeness | 必需组件/材料/源/物理列表完整 |
| G4-B | No Unapproved Simplification | 简化策略审计 |
| G4-C | Geometry Interface | 母子体积接口一致性 |
| G4-D | Overlap Policy | 无体积重叠 |
| G4-E | Evidence Traceability | 每个参数有证据来源 |
| G4-F | Code Module Boundary | 代码模块边界清晰 |
| G4-G | No Magic Number | 无硬编码物理常数 |

## Review Artifacts

每次成功运行后，GitHub-reviewable 产物自动收集到：

```
review_artifacts/g4_complex_model/latest/
├── README.md                          # 产物说明
├── artifact_manifest.json             # 文件清单
├── review_report.json                 # 收集状态摘要
└── output/
    ├── g4_model_ir.json               # 完整 Model IR
    ├── gate_results.json              # 19 道门禁结果
    ├── component_specs_summary.json   # 组件概要
    ├── no_simplification_report.json  # 简化策略审计
    ├── geometry_interface_report.json # 几何接口报告
    ├── evidence_traceability_report.json # 证据追溯
    ├── construction_ledger.json       # 构建审计
    └── model_review_report.md         # 模型审查报告
```

## 快速开始

```bash
# 安装依赖
pip install -e ".[dev]"

# 配置环境变量
cp .env.example .env

# 运行全部测试（178 个测试）
pytest tests/

# 仅运行单元测试
pytest tests/unit/

# 仅运行 E2E 测试
pytest tests/e2e/

# 运行 Agent
python -m agent_core.main "模拟 100 MeV 质子束垂直入射硅探测器"
```

## 项目结构

```
RadAgent/
├── agent_core/
│   ├── graph/
│   │   ├── main_graph.py          # 主图构建（调度器）
│   │   ├── main_state.py          # 主状态定义（路径化）
│   │   ├── main_routes.py         # 条件路由
│   │   └── subgraphs/             # 8 个子图构建器
│   ├── context/                   # Context Subgraph
│   ├── planning/                  # Task Planning Subgraph
│   ├── g4_modeling/               # G4 Modeling Subgraph（15 节点）
│   │   └── schemas/               # G4ModelIR, ComponentSpec 等
│   ├── g4_codegen/                # G4 Codegen Subgraph
│   ├── patching/                  # Patch Subgraph
│   ├── gates/                     # Gate Validation Subgraph
│   ├── artifacts/                 # Artifact Subgraph
│   ├── reports/                   # Report Subgraph
│   ├── config/                    # 配置（workspace 路径）
│   ├── validators/                # 验证器（patch, file permission）
│   ├── policies/                  # 策略文件（文件权限区域）
│   └── main.py                    # 入口点
├── review_artifacts/              # GitHub-reviewable 产物
├── simulation_workspace/          # 运行时工作空间（不入 Git）
├── tests/
│   ├── unit/                      # 单元测试（175 个）
│   └── e2e/                       # 端到端测试（3 个）
└── benchmark_suite/               # 基准测试套件
```

## 测试覆盖

| 测试文件 | 覆盖范围 |
|----------|---------|
| test_main_graph_subgraph_routing.py | 主图条件路由（20+ 测试） |
| test_subgraph_compilation.py | 子图编译和状态结构 |
| test_context_subgraph.py | RAG/Web 上下文收集 |
| test_task_planning_subgraph.py | 任务解析和验证 |
| test_gate_subgraph.py | 基础门禁 + G4 建模门禁 |
| test_patch_subgraph.py | Patch 加载/审查/应用 |
| test_report_subgraph.py | 报告生成 |
| test_artifact_subgraph.py | 产物收集 |
| test_architecture_invariants.py | 架构不变性（29 项检查） |
| test_e2e_pipeline.py | 端到端管线流程 |
| g4_modeling/ | G4 建模子图完整测试（81 个） |

## 范围说明

- **当前支持**: Geant4 复杂建模
- **保留范围**: TCAD Sentaurus、ngspice（代码预留，功能未实现）
- 报告会标注 TCAD/SPICE 为 "reserved for later implementation"

## 许可证

MIT
