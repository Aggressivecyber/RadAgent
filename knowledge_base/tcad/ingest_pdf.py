#!/usr/bin/env python3
"""
TCAD RAG 增量导入 PDF
- 读取 PDF 解析后的 Markdown 文件
- 转为 JSONL
- 增量嵌入到现有 tcad_index.db（不删旧数据！）
"""

import json
import os
import pickle
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "tcad_index.db"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "bge-m3"
BATCH_SIZE = 32
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50


def estimate_tokens(text: str) -> int:
    return len(text) // 4


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if estimate_tokens(text) <= chunk_size:
        return [text]
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = ""
    current_tokens = 0
    for para in paragraphs:
        para_tokens = estimate_tokens(para)
        if para_tokens > chunk_size:
            sentences = para.replace('. ', '.\n').replace('! ', '!\n').replace('? ', '?\n').split('\n')
            for sent in sentences:
                sent_tokens = estimate_tokens(sent)
                if current_tokens + sent_tokens > chunk_size and current_chunk:
                    chunks.append(current_chunk.strip())
                    overlap_text = current_chunk[-overlap * 4:] if overlap > 0 else ""
                    current_chunk = overlap_text + "\n" + sent
                    current_tokens = estimate_tokens(current_chunk)
                else:
                    current_chunk += "\n" + sent if current_chunk else sent
                    current_tokens += sent_tokens
        else:
            if current_tokens + para_tokens > chunk_size and current_chunk:
                chunks.append(current_chunk.strip())
                overlap_text = current_chunk[-overlap * 4:] if overlap > 0 else ""
                current_chunk = overlap_text + "\n\n" + para
                current_tokens = estimate_tokens(current_chunk)
            else:
                current_chunk += "\n\n" + para if current_chunk else para
                current_tokens += para_tokens
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    return chunks


def embed_texts_batch(texts: list[str]) -> list[list[float]]:
    embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        batch = [t[:8000] if len(t) > 8000 else t for t in batch]
        payload = json.dumps({"model": EMBED_MODEL, "input": batch}).encode('utf-8')
        req = urllib.request.Request(OLLAMA_EMBED_URL, data=payload, headers={"Content-Type": "application/json"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    result = json.loads(resp.read().decode('utf-8'))
                    batch_embeddings = result.get("embeddings", [])
                    embeddings.extend(batch_embeddings)
                    print(f"    [{i+len(batch_embeddings)}/{len(texts)}] 已嵌入", file=sys.stderr)
                    break
            except Exception as e:
                if attempt < 2:
                    print(f"    [RETRY] attempt {attempt+1}: {e}", file=sys.stderr)
                    time.sleep(3)
                else:
                    print(f"    [ERROR] 跳过 {len(batch)} 条: {e}", file=sys.stderr)
                    embeddings.extend([None] * len(batch))
    return embeddings


def main():
    # 参数：markdown 目录列表
    md_dirs = sys.argv[1:]
    if not md_dirs:
        print("用法: python3 ingest_pdf.py <md_dir1> [md_dir2] ...")
        sys.exit(1)

    # 收集所有 markdown 文件
    all_docs = []
    for md_dir in md_dirs:
        md_dir = Path(md_dir)
        if not md_dir.exists():
            print(f"[WARN] 目录不存在: {md_dir}", file=sys.stderr)
            continue
        # 查找 markdown 文件
        for md_file in sorted(md_dir.rglob("*.md")):
            content = md_file.read_text(encoding='utf-8', errors='ignore')
            if len(content.strip()) < 50:
                continue
            # 从文件名推断标题
            title = md_file.stem
            # 查找同目录下的 PDF 文件名作为来源
            parent_name = md_dir.name
            all_docs.append({
                "source": f"pdf_{parent_name}",
                "file_path": str(md_file),
                "title": title,
                "content": content,
                "metadata": json.dumps({
                    "type": "pdf",
                    "pdf_name": parent_name,
                    "md_file": md_file.name,
                    "format": "markdown"
                })
            })

    if not all_docs:
        print("[ERROR] 未找到有效的 Markdown 文件")
        sys.exit(1)

    print(f"找到 {len(all_docs)} 个 Markdown 文件")

    # 分块
    all_chunks = []
    for doc in all_docs:
        chunks = chunk_text(doc["content"])
        for chunk in chunks:
            if len(chunk.strip()) < 20:
                continue
            all_chunks.append({
                "source": doc["source"],
                "title": doc["title"],
                "content": chunk,
                "metadata": doc["metadata"]
            })

    print(f"分块后: {len(all_chunks)} 个块")

    # 嵌入
    print("\n开始嵌入...")
    texts = [c["content"] for c in all_chunks]
    embeddings = embed_texts_batch(texts)

    # 写入数据库（增量！不删旧数据！）
    if not DB_PATH.exists():
        print(f"[ERROR] 数据库不存在: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    inserted = 0
    for chunk, emb in zip(all_chunks, embeddings):
        if emb is None:
            continue
        emb_blob = pickle.dumps(np.array(emb, dtype=np.float32))
        c.execute("""
            INSERT INTO documents (source, title, content, embedding, metadata)
            VALUES (?, ?, ?, ?, ?)
        """, (chunk["source"], chunk["title"], chunk["content"], emb_blob, chunk["metadata"]))
        inserted += 1

    # 更新 sources 统计
    source_counts = {}
    for chunk in all_chunks:
        s = chunk["source"]
        source_counts[s] = source_counts.get(s, 0) + 1
    for source, count in source_counts.items():
        # 检查是否已存在
        c.execute("SELECT doc_count FROM sources WHERE source=?", (source,))
        row = c.fetchone()
        if row:
            c.execute("UPDATE sources SET doc_count=doc_count+?, last_updated=datetime('now') WHERE source=?", (count, source))
        else:
            c.execute("INSERT INTO sources (source, doc_count, last_updated) VALUES (?, ?, datetime('now'))", (source, count))

    conn.commit()
    conn.close()

    print(f"\n完成! 增量写入 {inserted} 个块")
    print(f"数据库: {DB_PATH} ({DB_PATH.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
