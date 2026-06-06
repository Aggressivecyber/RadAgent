#!/usr/bin/env python3
"""
Geant4 RAG MCP Server (stdio)
- 实现 MCP stdio JSON-RPC 协议
- 工具: search_geant4, keyword_search, get_document, list_sources, ask_geant4, generate_geant4_code
"""

import json
import os
import pickle
import sqlite3
import sys
from pathlib import Path

import numpy as np

DB_PATH = Path(__file__).parent / "data" / "geant4_index.db"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "bge-m3"

# 智谱 LLM API 配置
LLM_API_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
LLM_API_KEY = "f5dc034a22df47ac8cf98c37710e0bc6.crvx5afiTuITC247"
LLM_MODEL = "glm-5-turbo"


# ============================================================================
# 嵌入和搜索
# ============================================================================

def get_embedding(text: str) -> list[float]:
    """调用 Ollama 获取文本嵌入向量"""
    import urllib.request

    if len(text) > 8000:
        text = text[:8000]

    payload = json.dumps({
        "model": EMBED_MODEL,
        "input": text
    }).encode('utf-8')

    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode('utf-8'))
        embeddings = result.get("embeddings", [[]])
        if embeddings and embeddings[0]:
            return embeddings[0]
        return result.get("embedding", embeddings[0] if embeddings else [])


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """计算余弦相似度"""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def search_documents(query: str, top_k: int = 5) -> list[dict]:
    """语义搜索文档"""
    if not DB_PATH.exists():
        return [{"error": "数据库不存在，请先运行 build_index.py"}]

    query_emb = np.array(get_embedding(query), dtype=np.float32)

    conn = sqlite3.connect(str(DB_PATH))
    try:
        c = conn.cursor()
        c.execute("SELECT id, source, title, content, embedding, metadata FROM documents")
        rows = c.fetchall()

        if not rows:
            return []

        results = []
        for row in rows:
            doc_id, source, title, content, emb_blob, metadata = row
            try:
                doc_emb = pickle.loads(emb_blob)
                score = cosine_similarity(query_emb, doc_emb)
                results.append({
                    "doc_id": doc_id,
                    "source": source,
                    "title": title,
                    "content": content[:500] + "..." if len(content) > 500 else content,
                    "relevance_score": round(score, 4),
                    "metadata": json.loads(metadata) if metadata else {}
                })
            except Exception:
                continue

        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        return results[:top_k]

    finally:
        conn.close()


def get_document(doc_id: int) -> dict:
    """获取完整文档内容"""
    if not DB_PATH.exists():
        return {"error": "数据库不存在"}

    conn = sqlite3.connect(str(DB_PATH))
    try:
        c = conn.cursor()
        c.execute("SELECT id, source, title, content, metadata FROM documents WHERE id = ?", (doc_id,))
        row = c.fetchone()
        if not row:
            return {"error": f"文档 ID {doc_id} 不存在"}

        return {
            "doc_id": row[0],
            "source": row[1],
            "title": row[2],
            "content": row[3],
            "metadata": json.loads(row[4]) if row[4] else {}
        }
    finally:
        conn.close()


def list_sources() -> dict:
    """列出所有数据源"""
    if not DB_PATH.exists():
        return {"error": "数据库不存在"}

    conn = sqlite3.connect(str(DB_PATH))
    try:
        c = conn.cursor()
        c.execute("SELECT source, COUNT(*) FROM documents GROUP BY source")
        sources = {row[0]: row[1] for row in c.fetchall()}

        c.execute("SELECT COUNT(*) FROM documents")
        total = c.fetchone()[0]

        db_size = DB_PATH.stat().st_size / 1024 / 1024

        return {
            "total_documents": total,
            "total_chunks": total,
            "database_size_mb": round(db_size, 1),
            "sources": sources
        }
    finally:
        conn.close()


def keyword_search_func(keyword: str, top_k: int = 10) -> list[dict]:
    """基于 SQL LIKE 的关键词搜索"""
    if not DB_PATH.exists():
        return [{"error": "数据库不存在，请先运行 build_index.py"}]

    conn = sqlite3.connect(str(DB_PATH))
    try:
        c = conn.cursor()
        pattern = f"%{keyword}%"
        c.execute("""
            SELECT id, source, title, content, metadata
            FROM documents
            WHERE content LIKE ? OR title LIKE ?
            ORDER BY CASE
                WHEN title LIKE ? THEN 0
                ELSE 1
            END
            LIMIT ?
        """, (pattern, pattern, pattern, top_k))
        rows = c.fetchall()

        results = []
        for row in rows:
            doc_id, source, title, content, metadata = row
            results.append({
                "doc_id": doc_id,
                "source": source,
                "title": title,
                "content": content[:500] + "..." if len(content) > 500 else content,
                "metadata": json.loads(metadata) if metadata else {}
            })
        return results
    finally:
        conn.close()


# ============================================================================
# MCP JSON-RPC 协议实现 (stdio)
# ============================================================================

def send_response(result: dict, req_id: int | None = None):
    """发送 JSON-RPC 响应"""
    response = {"jsonrpc": "2.0", "id": req_id}
    if isinstance(result, dict) and "error" in result and "code" in result.get("error", {}):
        response["error"] = result["error"]
    else:
        response["result"] = result
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def send_notification(method: str, params: dict):
    """发送 JSON-RPC 通知"""
    notification = {"jsonrpc": "2.0", "method": method, "params": params}
    sys.stdout.write(json.dumps(notification) + "\n")
    sys.stdout.flush()


def handle_request(request: dict):
    """处理单个 JSON-RPC 请求"""
    method = request.get("method", "")
    params = request.get("params", {})
    req_id = request.get("id")

    if method == "initialize":
        send_response({
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "geant4-rag",
                "version": "1.0.0"
            }
        }, req_id)

    elif method == "notifications/initialized":
        pass

    elif method == "tools/list":
        send_response({
            "tools": [
                {
                    "name": "search_geant4",
                    "description": "搜索 Geant4 相关文档。支持语义搜索手册、教程和代码示例。返回最相关的文档片段及其来源信息。",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "搜索查询，支持自然语言，如 'G4EmStandardPhysics electromagnetic physics list' 或 'SteppingVerbose tracking'"
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "返回结果数量，默认 5",
                                "default": 5
                            }
                        },
                        "required": ["query"]
                    }
                },
                {
                    "name": "keyword_search",
                    "description": "基于 SQL LIKE 的关键词精确搜索，补充语义搜索。适合搜索特定命令名、参数名、文件名等。",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": "搜索关键词，如 'G4Box', 'G4Step', 'RunAction'"
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "返回结果数量，默认 10",
                                "default": 10
                            }
                        },
                        "required": ["keyword"]
                    }
                },
                {
                    "name": "get_document",
                    "description": "根据文档 ID 获取完整的文档内容。用于获取 search_geant4 返回结果的完整内容。",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "doc_id": {
                                "type": "integer",
                                "description": "文档 ID（从 search_geant4 结果中获取）"
                            }
                        },
                        "required": ["doc_id"]
                    }
                },
                {
                    "name": "list_sources",
                    "description": "列出所有 Geant4 数据源及其文档数量统计。",
                    "inputSchema": {
                        "type": "object",
                        "properties": {}
                    }
                },
                {
                    "name": "ask_geant4",
                    "description": "Geant4 专家问答（Agent 模式）。自动进行查询改写、多路检索、思维链推理，给出专业回答。适合复杂技术问题。",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Geant4 相关问题，支持中英文，如 '如何定义自定义物理过程' 或 'how to score dose in a volume'"
                            }
                        },
                        "required": ["query"]
                    }
                },
                {
                    "name": "generate_geant4_code",
                    "description": "根据需求生成 Geant4 仿真代码（C++）。自动检索代码示例并结合需求生成完整项目代码，带中文注释。",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "requirements": {
                                "type": "string",
                                "description": "代码生成需求描述，如 'proton therapy dose calculation in water phantom' 或 '硅探测器伽马射线能量沉积仿真'"
                            }
                        },
                        "required": ["requirements"]
                    }
                }
            ]
        }, req_id)

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        try:
            if tool_name == "search_geant4":
                query = arguments.get("query", "")
                top_k = arguments.get("top_k", 5)
                results = search_documents(query, top_k)

                text_parts = []
                for r in results:
                    text_parts.append(
                        f"[ID:{r['doc_id']}] {r['title']}\n"
                        f"来源: {r['source']} | 相关度: {r['relevance_score']}\n"
                        f"{r['content']}\n"
                    )

                send_response({
                    "content": [{"type": "text", "text": "\n---\n".join(text_parts) if text_parts else "未找到相关文档"}]
                }, req_id)

            elif tool_name == "keyword_search":
                keyword = arguments.get("keyword", "")
                top_k = arguments.get("top_k", 10)
                results = keyword_search_func(keyword, top_k)

                text_parts = []
                for r in results:
                    text_parts.append(
                        f"[ID:{r['doc_id']}] {r['title']}\n"
                        f"来源: {r['source']}\n"
                        f"{r['content']}\n"
                    )

                send_response({
                    "content": [{"type": "text", "text": "\n---\n".join(text_parts) if text_parts else "未找到相关文档"}]
                }, req_id)

            elif tool_name == "get_document":
                doc_id = arguments.get("doc_id")
                if doc_id is None:
                    send_response({"error": {"code": -32602, "message": "缺少 doc_id 参数"}}, req_id)
                    return
                doc = get_document(doc_id)
                if "error" in doc:
                    send_response({"error": {"code": -32602, "message": doc["error"]}}, req_id)
                    return
                text = (
                    f"ID: {doc['doc_id']}\n"
                    f"标题: {doc['title']}\n"
                    f"来源: {doc['source']}\n"
                    f"元数据: {json.dumps(doc.get('metadata', {}), ensure_ascii=False)}\n\n"
                    f"{doc['content']}"
                )
                send_response({
                    "content": [{"type": "text", "text": text}]
                }, req_id)

            elif tool_name == "list_sources":
                info = list_sources()
                if "error" in info:
                    send_response({"error": {"code": -32603, "message": info["error"]}}, req_id)
                    return
                text = (
                    f"Geant4 RAG 数据源统计 (Geant4 11.3.2 文档)\n"
                    f"总文档块数: {info['total_chunks']}\n"
                    f"数据库大小: {info['database_size_mb']} MB\n\n"
                )
                for source, count in info.get("sources", {}).items():
                    text += f"  - {source}: {count} 块\n"
                send_response({
                    "content": [{"type": "text", "text": text}]
                }, req_id)

            elif tool_name == "ask_geant4":
                query = arguments.get("query", "")
                if not query:
                    send_response({"error": {"code": -32602, "message": "缺少 query 参数"}}, req_id)
                    return
                try:
                    from geant4_agent import run_agent
                    answer = run_agent(query, verbose=False)
                    send_response({
                        "content": [{"type": "text", "text": answer}]
                    }, req_id)
                except Exception as e:
                    send_response({"error": {"code": -32603, "message": f"Agent 执行错误: {str(e)}"}}, req_id)

            elif tool_name == "generate_geant4_code":
                requirements = arguments.get("requirements", "")
                if not requirements:
                    send_response({"error": {"code": -32602, "message": "缺少 requirements 参数"}}, req_id)
                    return
                try:
                    from geant4_generator import generate_geant4_code
                    code = generate_geant4_code(requirements)
                    send_response({
                        "content": [{"type": "text", "text": code}]
                    }, req_id)
                except Exception as e:
                    send_response({"error": {"code": -32603, "message": f"代码生成错误: {str(e)}"}}, req_id)

            else:
                send_response({"error": {"code": -32601, "message": f"未知工具: {tool_name}"}}, req_id)

        except Exception as e:
            send_response({"error": {"code": -32603, "message": f"工具执行错误: {str(e)}"}}, req_id)

    elif method == "ping":
        send_response({}, req_id)

    else:
        send_response({"error": {"code": -32601, "message": f"未知方法: {method}"}}, req_id)


def main():
    """主循环：读取 stdin 的 JSON-RPC 请求"""
    sys.stdout = open(sys.stdout.fileno(), 'w', buffering=1)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            handle_request(request)
        except json.JSONDecodeError as e:
            send_response({"error": {"code": -32700, "message": f"JSON 解析错误: {e}"}})
        except Exception as e:
            send_response({"error": {"code": -32603, "message": f"内部错误: {str(e)}"}})


if __name__ == "__main__":
    main()
