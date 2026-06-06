# TCAD RAG

Semantic search over Synopsys TCAD Sentaurus documentation and code examples.

## What it provides

- **search_tcad(query, top_k=5)** — Search manuals, training docs, and application code examples using natural language
- **get_document(doc_id)** — Retrieve full document content by ID
- **list_sources()** — Show data source statistics

## Data sources

| Source | Type | Content |
|--------|------|---------|
| olh_sentaurus | Manual | Sentaurus online help (SDE, SDevice, SProcess, SVisual, SWB, etc.) |
| code | Examples | Applications Library (.cmd/.tcl files for FinFET, CMOS, Bipolar, Solar, etc.) |

## Setup

1. Run `python3 preprocess.py` to convert HTML/code to JSONL
2. Run `python3 build_index.py` to build the vector index (requires Ollama with bge-m3 running)
3. MCP server runs automatically via stdio transport

## Query examples

- "FinFET mesh refinement settings"
- "sprocess ion implantation commands"
- "how to define doping profiles in SDE"
- "Sentaurus Device physics models for impact ionization"
- "CMOS process flow example"

## Architecture

```
TCAD Data (HTML/Code)
    → preprocess.py → JSONL chunks
    → build_index.py → SQLite + bge-m3 embeddings
    → tcad_rag_mcp.py → MCP server (stdio)
```
