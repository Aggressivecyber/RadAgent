---
name: geant4-rag
description: Geant4 蒙特卡洛粒子输运仿真 RAG 知识库。通过 MCP 提供语义搜索、关键词搜索、文档获取、专家问答和代码生成。用于 Geant4 4.10/11.x 物理过程、几何构建、探测器仿真、剂量学等。
---

# Geant4 RAG MCP Server

基于 Geant4 11.3.2 官方文档构建的 RAG 知识库，提供语义搜索和专家问答能力。

## 前置条件

- Ollama 运行中，已拉取 `bge-m3` 模型：`ollama pull bge-m3`
- 依赖：`numpy`
- 数据文件：`data/raw/` 下有 Geant4 文档 HTML 文件（143 个）

## 建索引

```bash
cd ~/.openclaw/workspace/skills/geant4-rag
python build_index.py
```

输出：`data/geant4_index.db`

## MCP Server 配置

在 OpenClaw 配置中添加：

```json
{
  "mcpServers": {
    "geant4-rag": {
      "command": "python3",
      "args": ["/home/rylan/.openclaw/workspace/skills/geant4-rag/geant4_rag_mcp.py"]
    }
  }
}
```

## 可用工具

| 工具名 | 说明 |
|--------|------|
| `search_geant4` | 语义搜索 Geant4 文档 |
| `keyword_search` | 关键词精确搜索 |
| `get_document` | 按 ID 获取完整文档 |
| `list_sources` | 列出数据源统计 |
| `ask_geant4` | Agent 模式专家问答 |
| `generate_geant4_code` | 生成 Geant4 仿真 C++ 代码 |

## 文件结构

```
geant4-rag/
├── SKILL.md              # 本文件
├── build_index.py        # 索引构建脚本
├── geant4_rag_mcp.py     # MCP Server
└── data/
    ├── raw/              # 原始 HTML 文档（143 个）
    └── geant4_index.db   # 向量索引数据库（构建后生成）
```
