# CLAUDE.md — RadAgent 编码规范

> 本文件是 RadAgent 项目的开发规范。所有新增模块、节点、工具必须遵循。

## 项目概述

RadAgent 是一个基于 LangGraph 的航天辐照仿真智能体。用户输入自然语言描述，系统自动完成：
**意图解析 → 屏蔽结构设计 → 轨道环境查询 → 参数确认 → Geant4 模板渲染 → 编译运行 → 结果分析 → 报告生成**

LLM 使用 DeepSeek（`deepseek-chat`），Geant4 版本 11.3。

## 目录结构

```
radagent/
├── __init__.py              # 版本号
├── __main__.py              # 入口委托
├── main.py                  # CLI 交互循环
├── config.py                # 环境变量、路径、超时
├── log.py                   # 日志系统（按会话分目录）
├── schemas.py               # 所有 frozen dataclass（DTO）
├── state.py                 # 主图 RadAgentState
├── graph.py                 # 主图构建
├── nodes/                   # 主图节点（确定性 + LLM）
│   ├── parameterize.py      # 模板渲染
│   ├── build_run.py         # 编译 + 运行
│   ├── analyze.py           # 结果分析 + 异常检测
│   └── report.py            # 报告生成 + 人工审核
├── subgraphs/               # 调研子图
│   ├── research.py          # 子图构建
│   ├── state.py             # ResearchState
│   ├── parse_intent.py      # 意图提取
│   ├── design_schema.py     # 屏蔽几何设计
│   ├── research_params.py   # 轨道查询 + 场景生成
│   └── confirm_params.py    # 用户确认
├── tools/                   # 纯工具函数（无 state 依赖）
│   ├── geant4_tools.py      # 模板渲染、编译、运行、解析
│   ├── knowledge.py         # 材料/粒子/轨道知识库
│   ├── orbit_query.py       # 轨道辐射查询（SpacePy / 降级）
│   └── web_search.py        # DuckDuckGo 搜索
├── rag/                     # Geant4 RAG 检索
│   └── search.py            # SQLite + Ollama bge-m3
└── templates/               # Geant4 C++ 模板
    └── multilayer_shield/   # 多层屏蔽模板
```

## 架构规则

### 1. 三层分离

| 层 | 职责 | 文件位置 | 能访问 |
|---|---|---|---|
| **节点** | 读写 state，决定路由（Command/goto） | `nodes/`, `subgraphs/` | state, tools, log, schemas |
| **工具** | 纯函数，无 state 依赖 | `tools/` | config, schemas |
| **Schema** | 不可变数据定义 | `schemas.py` | 无依赖 |

**禁止**：
- tools 直接读写 LangGraph state
- nodes 包含业务计算逻辑（应提取到 tools）
- schemas 导入 nodes 或 tools

### 2. 节点函数签名

所有节点函数必须遵循统一签名：

```python
from radagent.log import log_node_entry, log_node_exit, log_info, log_error

_NODE = "node_name"  # 用于日志标识

def node_name(state: RadAgentState) -> Command[Literal["next_node", "..."]]:
    """一行中文描述"""
    log_node_entry(_NODE, state)

    # ... 业务逻辑 ...

    update = {"key": value}
    log_node_exit(_NODE, "next_node", update)
    return Command(update=update, goto="next_node")
```

**规则**：
- 节点入口必须调 `log_node_entry`
- 节点出口必须调 `log_node_exit`
- 中间日志用 `log_info` / `log_error`
- LLM 调用必须调 `log_llm_call`（记录 prompt + response）
- 禁止使用 `print()`，全部用日志

### 3. 路由（Command）

使用 `Command` 动态路由，不使用静态边（除了 START 和无分支边）：

```python
# 正常流转
return Command(update={...}, goto="next_node")

# 重试
return Command(update={"parse_error": msg}, goto="self_node")

# 终止
return Command(update={...}, goto="__end__")
```

### 4. State 规范

- 主图 state: `RadAgentState`（`state.py`）
- 子图 state: `ResearchState`（`subgraphs/state.py`）
- 列表字段必须用 `Annotated[list[T], operator.add]`（累加而非覆盖）
- 修改 state 只通过 `Command(update={...})`，禁止直接 mutate

## 数据规范

### Schema 定义（schemas.py）

- **所有 dataclass 必须 `frozen=True`**（不可变）
- 有默认值的字段使用 `field(default_factory=...)`
- 每个字段一行中文注释
- 不要嵌套过深，扁平优先
- tuple 优先于 list（不可变）

### 命名

| 类型 | 风格 | 示例 |
|---|---|---|
| 文件名 | `snake_case.py` | `build_run.py` |
| 类名 | `PascalCase` | `SimulationPlan` |
| 函数/变量 | `snake_case` | `build_geant4()` |
| 节点名（graph） | `snake_case` | `"build_and_run"` |
| 常量 | `UPPER_SNAKE` | `GEANT4_SOURCE_SCRIPT` |
| 私有函数 | `_leading_underscore` | `_check_anomalies()` |

### 类型注解

- **所有函数签名必须加类型注解**
- 使用 `str | None` 而非 `Optional[str]`
- 使用 `tuple[T, ...]` 表示不可变序列
- 导入用 `from __future__ import annotations`（延迟解析）

## 日志规范

### 日志系统（log.py）

每次运行自动创建 `logs/session_YYYYMMDD_HHMMSS/`，包含：

```
├── pipeline.log              # 全局时序（所有节点混合）
├── 01_parse_intent.log       # 节点独立日志
├── ...
└── state_snapshots/          # JSON state 快照
    ├── 01_parse_intent_entry.json
    └── 01_parse_intent_exit.json
```

### 日志 API

```python
from radagent.log import (
    init_session_log,    # main.py 调用一次
    log_node_entry,      # 节点进入
    log_node_exit,       # 节点退出
    log_info,            # 一般信息 → 节点日志 + pipeline.log
    log_error,           # 错误 → 节点日志 + pipeline.log
    log_debug,           # 调试 → 仅节点日志
    log_llm_call,        # LLM prompt + response
    get_logger,          # 获取原生 logger
)
```

### 工具函数日志

工具函数使用标准 `logging.getLogger("radagent.node.tools")`：

```python
import logging
logger = logging.getLogger("radagent.node.tools")

def some_tool(...):
    logger.info("开始执行...")
    logger.error("失败: %s", error)
```

## LLM 使用规范

### 初始化

统一在模块顶部 try/except 初始化：

```python
try:
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(
        model=DEEPSEEK_MODEL,
        base_url=DEEPSEEK_BASE_URL,
        api_key=DEEPSEEK_API_KEY,
        temperature=0,  # 提取类用 0，生成类用 0.3
    )
except Exception:
    llm = None
```

### Prompt 管理

- System prompt 定义为模块级常量（`SYSTEM_PROMPT = """..."""`）
- 用 `{placeholder}` 做模板变量，调用时 `.format()`
- Prompt 用中文描述要求，要求返回 JSON 时明确指定格式

### 输出解析

LLM 输出可能包在 markdown 代码块中，统一用：

```python
def _strip_markdown(content: str) -> str:
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return content
```

JSON 解析必须 try/except `json.JSONDecodeError`，失败时路由重试。

## Geant4 工具规范

### 模板渲染

- 模板目录: `radagent/templates/multilayer_shield/`
- `.tpl` 文件用 `string.Template`（`$VARIABLE` 语法）
- 渲染后 `.tpl` 后缀去掉（`DetectorConstruction.cc.tpl` → `DetectorConstruction.cc`）
- 非 `.tpl` 文件直接复制

### 编译运行

- 必须先 `source /etc/profile.d/geant4.sh`
- cmake + make 通过 `subprocess.run(shell=True, executable="/bin/bash")`
- 设置超时（`CMAKE_TIMEOUT=120s`, `RUN_TIMEOUT=300s`）
- 输出截断保留尾部（`stdout[-10000:]`, `stderr[-2000:]`）

### 结果解析

- 优先 CSV 文件解析（`radagent_events.csv`, `radagent_steps.csv`）
- 降级到 stdout 正则解析
- 所有物理量带单位转换表

## 错误处理

### 重试策略

- 编译失败: `goto="parameterize"`（重新渲染模板）
- 运行失败: `goto="build_and_run"`（重试运行）
- 解析失败: `goto="self"`（LLM 重试）
- 重试上限: `control.max_retries`（默认 3 次）

### parse_error 模式

所有错误信息通过 `parse_error` 字段在 state 中传递：

```python
return Command(
    update={"parse_error": f"具体错误描述: {detail[:200]}"},
    goto="retry_node",
)
```

## 新增模块检查清单

新增节点或工具时，逐项确认：

- [ ] 文件放置在正确目录（nodes/ 或 tools/ 或 subgraphs/）
- [ ] 函数签名有完整类型注解
- [ ] 节点入口/出口调用 log_node_entry/log_node_exit
- [ ] 无 `print()` 语句
- [ ] LLM 调用使用 log_llm_call 记录
- [ ] 错误通过 parse_error 传递，不抛异常中断图
- [ ] frozen dataclass 定义在 schemas.py
- [ ] 工具函数无 state 依赖
- [ ] 路由使用 Command，不使用静态边（无分支除外）
- [ ] 模块顶部 docstring 一行描述功能
