# TCAD Agentic RAG — 4-Phase 构建计划

## 项目目录
`~/.openclaw/workspace/skills/tcad-rag/`

## 现状
- Phase 1 基础 RAG 已有框架代码（preprocess.py, build_index.py, tcad_rag_mcp.py）
- 正在构建向量索引（300/5945 已完成，后台运行中）
- Ollama bge-m3 在 http://localhost:11434 运行

## Phase 1: 基础 RAG 完善（进行中）
- [x] preprocess.py — HTML→Markdown + 代码文件索引
- [x] build_index.py — 向量索引构建
- [x] tcad_rag_mcp.py — MCP Server
- [ ] 验证 MCP server 能正确检索和返回结果
- [ ] 修复可能的 bug
- [ ] 确保索引完整构建完成

## Phase 2: Query Rewrite（查询改写）
- [ ] 新增 `query_rewrite.py`
- [ ] 功能：将用户自然语言问题改写为适合向量检索的查询
  - 提取 TCAD 关键词（SDE, SProcess, SDevice, Physics section 名等）
  - 扩展同义词（如 "radiation damage" → "trap charge, TID, total ionizing dose"）
  - 多查询生成（一个用户问题 → 3个不同角度的检索查询）
- [ ] 集成到 MCP server 的 search_tcad 工具中

## Phase 3: ReAct Agent（核心 Agent 层）
- [ ] 新增 `tcad_agent.py` — ReAct Agent 核心
- [ ] Agent 能力：
  - 思维链推理（Thought → Action → Observation 循环）
  - 工具选择：search_tcad, search_code, keyword_search, get_document, list_sources
  - 自我评估：判断检索结果是否足够回答问题
  - 迭代检索：结果不够时自动换关键词/工具重试
  - 最多 5 轮迭代，防止无限循环
- [ ] 新增 MCP 工具 `ask_tcad(query)` — 对外暴露 Agent 接口
- [ ] Agent prompt engineering（TCAD 领域专用系统提示词）

## Phase 4: Code Generation（代码生成）
- [ ] 新增 `code_generator.py`
- [ ] 功能：
  - 检索到 TCAD 代码示例后，结合用户需求修改/生成新脚本
  - 输出格式：完整的 .cmd 文件，带中文注释
  - 参考多个代码示例进行组合
- [ ] MCP 工具 `generate_tcad_code(requirements)` — 生成 TCAD 脚本
- [ ] 支持 SDE（结构定义）+ SProcess（工艺）+ SDevice（器件仿真）完整流程生成

## 技术约束
- Python 3 标准库 + numpy
- Ollama bge-m3 嵌入（http://localhost:11434）
- LLM 用智谱 API（key: f5dc034a22df47ac8cf98c37710e0bc6.crvx5afiTuITC247）或 Ollama 本地模型
- MCP stdio 协议
- 中文注释

## 验收标准
1. `search_tcad("如何设置 NMOS 辐照陷阱模型")` → 返回相关手册 + 代码
2. `ask_tcad("帮我写一个 FinFET 的辐射效应仿真流程")` → Agent 自动检索 + 生成回答
3. `generate_tcad_code("CMOS inverter, 45nm, TID 100krad")` → 生成完整 TCAD 脚本
