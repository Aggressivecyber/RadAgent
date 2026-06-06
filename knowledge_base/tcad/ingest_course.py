#!/usr/bin/env python3
"""
仅将课程材料添加到 TCAD RAG 索引（增量模式，不重建全部）
"""

import hashlib
import json
import os
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "tcad_index.db"
JSONL_FILE = DATA_DIR / "course_materials.jsonl"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "bge-m3"
BATCH_SIZE = 5  # 小批量避免 OOM


def get_embedding(text: str) -> list | None:
    """调用 Ollama bge-m3 获取嵌入向量"""
    payload = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode()
    req = urllib.request.Request(OLLAMA_EMBED_URL, data=payload, 
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result.get("embedding")
    except Exception as e:
        print(f"  [ERROR] 嵌入失败: {e}", file=sys.stderr)
        return None


def main():
    if not JSONL_FILE.exists():
        print(f"[ERROR] 文件不存在: {JSONL_FILE}", file=sys.stderr)
        sys.exit(1)

    # 读取 JSONL
    with open(JSONL_FILE, 'r', encoding='utf-8') as f:
        docs = [json.loads(line) for line in f if line.strip()]
    print(f"读取 {len(docs)} 个文档", file=sys.stderr)

    # 分块（代码文件整文件一块）
    all_chunks = []
    for doc in docs:
        content = doc.get("content", "")
        if len(content) > 8000:
            content = content[:8000]
        if len(content.strip()) < 20:
            continue
        all_chunks.append({
            "source": doc.get("source", "course"),
            "title": doc.get("title", ""),
            "content": content,
            "metadata": doc.get("metadata", "{}"),
            "file_path": doc.get("file_path", ""),
            "content_hash": hashlib.md5(content.encode()).hexdigest()
        })
    
    print(f"分块后: {len(all_chunks)} 个块", file=sys.stderr)

    # 连接数据库
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    
    # 确保表存在
    c.execute('''CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT,
        title TEXT,
        content TEXT,
        embedding BLOB,
        metadata TEXT,
        file_path TEXT,
        content_hash TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_source ON documents(source)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_title ON documents(title)')
    conn.commit()

    # 检查已存在的
    c.execute("SELECT content_hash FROM documents WHERE source='course'")
    existing = set(row[0] for row in c.fetchall())
    print(f"数据库中已有 course 源记录: {len(existing)} 条", file=sys.stderr)

    # 过滤已存在的
    new_chunks = [ch for ch in all_chunks if ch["content_hash"] not in existing]
    print(f"需要新增: {len(new_chunks)} 个块", file=sys.stderr)

    if not new_chunks:
        print("没有新内容需要添加！", file=sys.stderr)
        conn.close()
        return

    # 批量嵌入并写入
    success = 0
    fail = 0
    total = len(new_chunks)
    
    for i in range(0, total, BATCH_SIZE):
        batch = new_chunks[i:i + BATCH_SIZE]
        
        for chunk in batch:
            emb = get_embedding(chunk["content"])
            if emb:
                emb_blob = json.dumps(emb).encode()
                c.execute(
                    "INSERT INTO documents (source, title, content, embedding, metadata, file_path, content_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (chunk["source"], chunk["title"], chunk["content"], emb_blob,
                     chunk["metadata"], chunk["file_path"], chunk["content_hash"])
                )
                success += 1
            else:
                fail += 1
        
        conn.commit()
        done = min(i + BATCH_SIZE, total)
        print(f"进度: {done}/{total} (成功: {success}, 失败: {fail})", file=sys.stderr)
        time.sleep(0.1)  # 避免 Ollama 过载

    conn.close()
    print(f"\n[完成] 新增 {success} 条, 失败 {fail} 条", file=sys.stderr)


if __name__ == "__main__":
    main()
