# Radiation Simulation Agent (RadAgent)

基于 LangGraph 的自主代码生成型辐照联合仿真智能体系统。

## 概述

RadAgent 是一个工程化 Agent 平台，能够：

1. 理解用户辐照仿真需求（自然语言输入）
2. 根据需求调用对应 RAG 知识库（Geant4 / TCAD / SPICE）
3. 自主生成仿真代码、命令文件、网表或数据转换脚本
4. 通过严格门禁（12 道门）检查代码正确性
5. 管理 Geant4 → TCAD → SPICE 之间的数据传递
6. 生成可复现仿真报告

## 架构

```
用户输入 → LangGraph 状态调度 → Task Spec → Simulation IR
    → RAG 路由 → Agent 自主代码生成 → Patch → 门禁检查
    → 小规模仿真 → 数据契约校验 → 正式仿真 → 报告
```

## MVP 进度

| MVP | 描述 | 状态 |
|-----|------|------|
| MVP-1 | Geant4 自主代码生成 + 门禁 | 🚧 开发中 |
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
# 编辑 .env 填入 API key

# 运行测试
pytest tests/

# 运行 Agent（示例）
python -m agent_core.main "模拟 10 MeV 质子垂直入射 300 微米硅片"
```

## 项目结构

```
radiation_sim_agent/
├── agent_core/           # 核心 Agent 代码
│   ├── graph/            # LangGraph 图定义
│   ├── nodes/            # LangGraph 节点
│   ├── tools/            # Agent 工具（RAG、Shell、Patch 等）
│   ├── schemas/          # 数据 Schema（Pydantic 模型）
│   ├── validators/       # 验证器（静态检查、数据契约、物理一致性）
│   └── policies/         # 策略文件（文件权限、门禁、RAG）
├── knowledge_base/       # RAG 知识库目录
├── simulation_workspace/ # 仿真工作空间
├── benchmark_suite/      # 基准测试套件
└── tests/                # 测试
```

## 门禁系统

共 12 道门禁，所有代码必须逐门通过：

| Gate | 名称 | 检查内容 |
|------|------|----------|
| 0 | RAG 充分性 | RAG 上下文是否足够 |
| 1 | Task Spec Schema | 任务规格是否完整 |
| 2 | Simulation IR Schema | 仿真中间表示是否完整 |
| 3 | Patch 格式 | Patch 格式是否正确 |
| 4 | 文件权限 | 是否遵守文件权限策略 |
| 5 | 静态检查 | 语法、格式、类型 |
| 6 | 编译/解析 | CMake/SPICE 语法检查 |
| 7 | 单元测试 | 核心功能单元测试 |
| 8 | 数据契约 | 数据包格式校验 |
| 9 | 小规模仿真 | Smoke test 仿真 |
| 10 | 基准回归 | 基准测试对比 |
| 11 | 物理一致性 | 物理合理性检查 |

## 数据契约

所有跨模块数据传递必须通过标准化数据契约：

- `g4_output_contract` — Geant4 输出包
- `g4_to_tcad_contract` — Geant4 → TCAD 映射
- `tcad_input_contract` — TCAD 输入包
- `tcad_output_contract` — TCAD 输出包
- `tcad_to_spice_contract` — TCAD → SPICE 映射
- `spice_output_contract` — SPICE 输出包

## 许可证

MIT
