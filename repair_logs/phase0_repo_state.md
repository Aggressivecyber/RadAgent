1c19784 feat: add Human Confirmation Subgraph — multi-round user approval for model assumptions
e533c74 fix: regenerate artifacts — 9 components, new gate schema, dev mode FAILED
b88cb5c fix: regenerate artifacts with new gate schema + fix e2e assertions
---
 M repair_logs/phase0_repo_state.md
---
agent_core/human_confirmation/__init__.py
agent_core/human_confirmation/nodes.py
agent_core/human_confirmation/prompts.py
agent_core/human_confirmation/reports.py
agent_core/human_confirmation/schemas.py
agent_core/human_confirmation/validators.py
---
agent_core/graph/__init__.py
agent_core/graph/main_graph.py
agent_core/graph/main_routes.py
agent_core/graph/main_state.py
agent_core/graph/subgraphs/artifact_graph.py
agent_core/graph/subgraphs/context_graph.py
agent_core/graph/subgraphs/g4_codegen_graph.py
agent_core/graph/subgraphs/g4_modeling_graph.py
agent_core/graph/subgraphs/gate_validation_graph.py
agent_core/graph/subgraphs/human_confirmation_graph.py
agent_core/graph/subgraphs/__init__.py
agent_core/graph/subgraphs/patch_graph.py
agent_core/graph/subgraphs/report_graph.py
agent_core/graph/subgraphs/task_planning_graph.py
