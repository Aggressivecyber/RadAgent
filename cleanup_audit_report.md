# RadAgent MVP-1 Cleanup Audit Report

Generated: 2026-06-06

## Summary

| Category | Hits | Must Fix | Compat Keep | Notes |
|----------|------|----------|-------------|-------|
| Legacy RAG names (g4rag/tcadrag/spicerag) | 18 | 16 | 2 (test asserts) | Rename tool files + update imports |
| Old rag_context_pack decision enum | 4 | 4 | 0 | "allow_with_warning" → tri-state |
| write_fix_patch reads web_context | 1 | 1 | 0 | Should read rag_error_context |
| Stub RAG tools (tcadrag/spicerag) | 2 | 2 | 0 | Rename + clarify MVP scope |
| simulation_workspace nested | 0 (files) | 0 | 0 | .gitignore already covers |
| Tracked job artifacts | 12 dirs | 12 | 0 | Add to .gitignore, clean |
| rag_context_pack.py old schema | 1 file | 1 | 0 | Update decision enum |
| .env.example old MCP endpoints | 3 lines | 3 | 0 | Update endpoint names |
| diff_content in patch schema | 12 refs | 0 | 12 | Compat keep, mark deprecated |

## Detailed Findings

### F-01: Legacy Tool File Names
- `agent_core/tools/g4rag_tool.py` — class `G4RAGTool`
- `agent_core/tools/tcadrag_tool.py` — class `TCADRAGTool`
- `agent_core/tools/spicerag_tool.py` — class `SPICERAGTool`
- **Action**: Rename to `geant4_rag_tool.py`, `tcad_rag_tool.py`, `spice_rag_tool.py`; update all imports

### F-02: write_fix_patch.py reads wrong state key
- Line 47: `error_context = state.get("web_context", [])`
- **Action**: Change to `state.get("rag_error_context", [])`

### F-03: rag_context_pack.py has old decision enum
- `Literal["allow", "allow_with_warning", "block"]`
- **Action**: Update to `Literal["allow_rag", "needs_web", "block_no_context"]`

### F-04: .env.example old MCP endpoint names
- `G4RAG_MCP_ENDPOINT`, `TCADRAG_MCP_ENDPOINT`, `SPICERAG_MCP_ENDPOINT`
- **Action**: Rename to `GEANT4_RAG_ENDPOINT`, `TCAD_RAG_ENDPOINT`, `SPICE_RAG_ENDPOINT`

### F-05: tcadrag_tool.py / spicerag_tool.py are stubs
- Return empty results, `available = False`
- **Action**: Rename, add docstring clarifying MVP-1 scope (Geant4 only)

### F-06: Tracked job artifacts in simulation_workspace/jobs/
- 12 job directories tracked in git
- **Action**: Update .gitignore pattern, remove tracked dirs

### F-07: rag_route.json save file
- `route_rag.py` line 22: saves `rag_route.json`
- **Action**: Rename to `rag_routing_result.json` for clarity

### F-08: retrieve_g4_context imports G4RAGTool
- Must update after tool rename
- **Action**: Update import path

### F-09: diff_content in code_patch.py
- `diff_content: str = ""` — kept for future diff-mode support
- **Action**: Mark `# Deprecated: MVP-1 uses json_file_replacement only`

### F-10: g4rag_tool.py docstring says "g4rag MCP server"
- **Action**: Update to "Geant4 RAG MCP server"

## Files Modified

| File | Action |
|------|--------|
| `agent_core/tools/g4rag_tool.py` | Rename → `geant4_rag_tool.py` |
| `agent_core/tools/tcadrag_tool.py` | Rename → `tcad_rag_tool.py` |
| `agent_core/tools/spicerag_tool.py` | Rename → `spice_rag_tool.py` |
| `agent_core/nodes/write_fix_patch.py` | Fix web_context → rag_error_context |
| `agent_core/schemas/rag_context_pack.py` | Update decision enum |
| `agent_core/nodes/retrieve_g4_context.py` | Update import |
| `agent_core/nodes/retrieve_error_context.py` | Update import |
| `agent_core/nodes/retrieve_tcad_context.py` | Update import |
| `agent_core/nodes/retrieve_spice_context.py` | Update import |
| `agent_core/nodes/route_rag.py` | Rename output file |
| `agent_core/schemas/code_patch.py` | Mark diff_content deprecated |
| `.env.example` | Update endpoint names |
| `.gitignore` | Tighten job artifact pattern |
| `simulation_workspace/jobs/` | Remove tracked dirs |
