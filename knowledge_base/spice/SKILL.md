---
name: ngspice-rag
description: ngspice SPICE 仿真 RAG 知识库。通过 MCP 提供语义搜索、关键词搜索、文档获取、专家问答和代码生成。用于 ngspice 42 电路仿真、DC/AC/Transient 分析、BSIM 模型、SPICE 网表编写等。
---

# ngspice RAG MCP Server

基于 ngspice 官方文档构建的 RAG 知识库，提供语义搜索和专家问答能力。

## 数据源

- **manual**: 244 块 — ngspice 用户手册
- **circuit**: 220 块 — 电路仿真示例
- **tutorial**: 76 块 — 教程
- **reference**: 12 块 — 参考文档
- **application**: 4 块 — 应用案例
- **developer**: 2 块 — 开发者文档
- **总计**: 558 块，数据库 3.9 MB

## MCP Server 配置

在 OpenClaw 配置中已添加：

```json
{
  "mcpServers": {
    "ngspice-rag": {
      "command": "python3",
      "args": ["/home/rylan/.openclaw/workspace/skills/ngspice-rag/ngspice_rag_mcp.py"]
    }
  }
}
```

## 可用 MCP 工具

| 工具名 | 说明 |
|--------|------|
| `search_ngspice` | 语义搜索 ngspice 文档，支持自然语言查询 |
| `keyword_search` | 关键词精确搜索（SPICE 命令、模型名、参数等） |
| `get_document` | 按文档 ID 获取完整内容 |
| `list_sources` | 列出数据源统计 |
| `ask_ngspice` | Agent 模式专家问答（自动查询改写+多路检索+思维链推理） |
| `generate_spice_code` | 根据需求生成 SPICE 网表代码，带中文注释 |

## 典型用法

### 1. 快速搜索
```
search_ngspice(query="MOSFET DC sweep analysis")
keyword_search(keyword=".tran")
```

### 2. 专家问答
```
ask_ngspice(query="如何仿真 CMOS 反相器的传输特性")
```

### 3. 生成网表
```
generate_spice_code(requirements="CMOS inverter transfer characteristic with 45nm technology")
```

## 适用场景

- ngspice 命令和语法查询
- SPICE 网表编写和调试
- 电路 DC/AC/Transient/Noise 分析
- BSIM3/BSIM4 模型参数
- 子电路（subckt）定义和使用
- 器件模型（MOSFET、BJT、Diode、RLC 等）
- 与 TCAD 联合仿真的 SPICE 网表对接

## 文件结构

```
ngspice-rag/
├── SKILL.md              # 本文件
├── ngspice_rag_mcp.py    # MCP Server
└── data/
    ├── raw/              # 原始文档
    └── ngspice_index.db  # 向量索引数据库
```
