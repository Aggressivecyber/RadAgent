# RadAgent 最终修复报告

## 一、总体修复说明

### Model Gateway
- 新增 `agent_core/models/` 统一模型调用模块
- 所有 LLM 调用统一走 `ModelGateway.call()`
- 禁止业务模块直接调用底层 LLM SDK/API

### Lite/Pro/Max 三档模型
- **LITE**: intent routing, simple extraction, naming (默认 dsv4lite)
- **PRO**: task planning, modeling, codegen (默认 dsv4pro)
- **MAX**: final review, gate diagnosis (默认 dsv4pro，后续可升级)
- 三档逻辑完全分离，通过环境变量可独立配置

### Intent Router
- 新增 `agent_core/intent/` LLM Intent Router 模块
- 使用 LITE 模型判断用户意图
- 规则只做 slash command / 空输入 / 模型失败兜底
- "你好" → smalltalk，不进入 Task Planning
- 仿真请求才进入完整 pipeline

### 主图
- 主图入口改为 `initialize_request → intent_router`
- 新增 5 个响应节点：chat_response, help_response, status_response, capability_response, clarification
- smalltalk/help/status/capability 直接响应后 END
- simulation_request 才进入 prepare_workspace

### REPL
- 自然语言输入先经过 intent router
- 只有 simulation_request 才等价于 /run
- "你好"不再进入仿真流程
- /confirm 禁止 Auto-approved，必须显式确认

### run_pipeline
- 使用 `compile_main_graph()` 而非 `build_main_graph().invoke()`
- "你好" 返回 smalltalk intent，不生成任何仿真 artifact

### Workspace
- run_mode / execution_mode 统一映射
- prepare_workspace 使用 WorkspaceManager

### Task Planning
- 失败保护：超过 3 次失败后进入 save_task_failure
- 不得保存成正常 task spec 继续流转

### Human Confirmation
- main_graph 真实接入 human_confirmation_subgraph
- 无用户确认不得 codegen
- route_after_human_confirmation 严格检查确认状态

### Codegen/Patch
- Codegen 输出 proposed_patch.changed_files[].new_content
- Patch 写入 08_geant4，输出 07_patch/applied_patch.json

### Gate
- 任意 fail → FAILED
- dev + critical skipped → PARTIAL
- acceptance/production + critical skipped → FAILED

### Artifact Collector
- ArtifactCollector 是唯一写 review_artifacts 的模块

### C++ Codegen
- 修复 OutputManager, MaterialRegistry, SensitiveDetector 空 include 问题

## 二、修改文件列表

- `agent_core/graph/main_state.py` - 新增 intent 相关字段
- `agent_core/graph/main_graph.py` - 新增 intent router 和响应节点
- `agent_core/graph/main_routes.py` - 新增 route_after_intent
- `agent_core/repl.py` - 自然语言走 intent router，禁止 Auto-approved
- `agent_core/naming.py` - 使用模型网关替代直接 HTTP 调用
- `agent_core/g4_modeling/nodes/requirement_capture_node.py` - 使用模型网关
- `agent_core/g4_modeling/nodes/geometry_decomposition_node.py` - 使用模型网关
- `agent_core/g4_modeling/nodes/physics_list_node.py` - 使用模型网关
- `scripts/run_pipeline.py` - 使用 compile_main_graph
- `.env` - 新增模型网关配置
- `.env.example` - 更新配置示例
- `.github/workflows/ci.yml` - 新增 model-gateway, intent, repl 测试任务
- `tests/unit/test_naming.py` - 更新 mock 目标
- `tests/unit/test_repl.py` - 更新测试适配新行为
- `tests/unit/test_context_subgraph.py` - 移除旧 LLM mock

## 三、新增文件列表

### 模型网关模块
- `agent_core/models/__init__.py`
- `agent_core/models/schemas.py`
- `agent_core/models/config.py`
- `agent_core/models/registry.py`
- `agent_core/models/client.py`
- `agent_core/models/gateway.py`
- `agent_core/models/errors.py`
- `agent_core/models/usage.py`
- `agent_core/models/prompts.py`

### Intent Router 模块
- `agent_core/intent/__init__.py`
- `agent_core/intent/schemas.py`
- `agent_core/intent/prompts.py`
- `agent_core/intent/fallback_rules.py`
- `agent_core/intent/router.py`
- `agent_core/intent/nodes.py`

### Response 模块
- `agent_core/response/__init__.py`
- `agent_core/response/nodes.py`

### 测试文件
- `tests/unit/test_model_config.py`
- `tests/unit/test_model_gateway.py`
- `tests/unit/test_model_tiers.py`
- `tests/unit/test_intent_router.py`
- `tests/e2e/test_hello_does_not_crash.py`
- `tests/e2e/test_run_pipeline_hello.py`
- `tests/e2e/test_repl_hello_does_not_crash.py`

### 修复日志
- `repair_logs/FINAL_REPAIR_REPORT.md`

## 四、测试结果

```
compileall: PASS
ruff: PASS (仅剩 scripts/ 中的预存问题)
unit: 720 passed, 1 skipped
model gateway: 15 passed
intent: 11 passed
hello E2E: 3 passed
run_pipeline hello: 2 passed
repl hello: 4 passed
pipeline dev: 2 passed
no human: 13 passed
human edit: 4 passed
repl: 67 passed
总计: 764 passed, 1 skipped
```

## 五、当前限制

- **Geant4 真实 build**: 未在本次修复中测试（需要 Geant4 环境）
- **TCAD/SPICE**: 仍为预留能力，未实现
- **production mode**: 未在本次修复中测试
- **max 模型**: 当前仍映射 dsv4pro，后续可升级更强模型

## 六、仍未解决问题

- 无（本轮 P0 清单全部完成）
