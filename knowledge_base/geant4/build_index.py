#!/usr/bin/env python3
"""
Geant4 RAG 向量索引构建脚本
- 读取 JSONL 文档（preprocess.py 生成）
- 分块：手册按 512 tokens 分块（重叠 50），代码文件整文件一块
- 调用 Ollama bge-m3 嵌入（GPU 加速）
- 存储到 SQLite (data/geant4_index.db)

增量更新说明：
  默认（无参数）:    增量模式（预处理+索引），只处理变化的源文件
  --skip-preprocess: 跳过预处理，仅对已有 JSONL 增量构建索引
  --rebuild:         删库重建，重新处理所有文档
  --prune:           清理 DB 中已不存在于源文件的孤儿记录
"""

import argparse
import hashlib
import json
import pickle
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from knowledge_base.geant4.paths import geant4_example_root  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "geant4_index.db"
CACHE_PATH = DATA_DIR / ".source_cache.json"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "bge-m3"
BATCH_SIZE = 10
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
CODE_MAX_CHARS = 8000
PREPROCESS_SCRIPT = Path(__file__).parent / "preprocess.py"


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数"""
    return len(text) // 4


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """将文本按段落/句子边界分块"""
    if estimate_tokens(text) <= chunk_size:
        return [text]

    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = ""
    current_tokens = 0

    for para in paragraphs:
        para_tokens = estimate_tokens(para)

        if para_tokens > chunk_size:
            sentences = (
                para.replace('. ', '.\n')
                .replace('! ', '!\n')
                .replace('? ', '?\n')
                .split('\n')
            )
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
    """批量调用 Ollama 嵌入 API（GPU 加速）"""
    embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        batch = [t[:8000] if len(t) > 8000 else t for t in batch]

        payload = json.dumps({
            "model": EMBED_MODEL,
            "input": batch
        }).encode('utf-8')

        req = urllib.request.Request(
            OLLAMA_EMBED_URL,
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        max_retries = 3
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    result = json.loads(resp.read().decode('utf-8'))
                    batch_embeddings = result.get("embeddings", [])
                    embeddings.extend(batch_embeddings)
                    print(f"    [{i+len(batch_embeddings)}/{len(texts)}] 已嵌入", file=sys.stderr)
                    break
            except (urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
                if attempt < max_retries - 1:
                    print(f"    [RETRY] 批量嵌入失败 (attempt {attempt+1}): {e}", file=sys.stderr)
                    time.sleep(3)
                else:
                    print(f"    [ERROR] 批量嵌入失败，跳过 {len(batch)} 条: {e}", file=sys.stderr)
                    embeddings.extend([None] * len(batch))

        if i + BATCH_SIZE < len(texts):
            time.sleep(0.05)

    return embeddings


def _scan_source_files() -> dict[str, tuple[float, int]]:
    """扫描所有源文件，返回 {路径: (mtime, size)} 映射"""
    sources = {}
    raw_dir = Path(__file__).parent / "data" / "raw"
    if raw_dir.exists():
        for f in raw_dir.rglob("*"):
            if f.is_file() and f.suffix in ('.html', '.htm', '.texi', '.cc', '.hh', '.cpp', '.h'):
                sources[str(f)] = (f.stat().st_mtime, f.stat().st_size)
    examples_dir = geant4_example_root()
    if examples_dir is not None:
        for f in examples_dir.rglob("*"):
            if f.is_file() and f.suffix in ('.cc', '.hh', '.cpp', '.h'):
                sources[str(f)] = (f.stat().st_mtime, f.stat().st_size)
    return sources


def _load_source_cache() -> dict[str, tuple[float, int]]:
    """加载源文件缓存"""
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _save_source_cache(cache: dict[str, tuple[float, int]]):
    """保存源文件缓存"""
    with open(CACHE_PATH, 'w') as f:
        json.dump(cache, f, indent=2)


def run_preprocess() -> bool:
    """增量运行预处理脚本。返回 True 表示有文件变化需要重建索引"""
    if not PREPROCESS_SCRIPT.exists():
        print("[WARN] preprocess.py 不存在，跳过预处理", file=sys.stderr)
        return True  # 无法判断，保守处理

    old_cache = _load_source_cache()
    new_sources = _scan_source_files()

    # 检测是否有变化
    changed = False
    deleted = set(old_cache.keys()) - set(new_sources.keys())

    for path, (mtime, size) in new_sources.items():
        old = old_cache.get(path)
        if old is None or old[0] != mtime or old[1] != size:
            changed = True
            break

    if deleted:
        changed = True

    if not changed:
        print(f"[增量预处理] 源文件无变化（{len(new_sources)} 个文件），跳过预处理")
        return False

    print("[增量预处理] 检测到变化（新增/修改/删除），运行 preprocess.py ...")
    print(f"  文件总数: {len(new_sources)}, 旧缓存: {len(old_cache)}, 删除: {len(deleted)}")

    result = subprocess.run(
        [sys.executable, str(PREPROCESS_SCRIPT)],
        capture_output=True, text=True, timeout=600
    )
    if result.stdout:
        print(result.stdout, end='')
    if result.stderr:
        print(result.stderr, end='', file=sys.stderr)
    if result.returncode != 0:
        print(f"[ERROR] preprocess.py 返回码 {result.returncode}", file=sys.stderr)
        return True  # 出错了，保守处理

    # 更新缓存
    _save_source_cache(new_sources)
    print(f"[增量预处理] 完成，缓存已更新 ({len(new_sources)} 个文件)")
    return True


def prune_orphaned_docs(conn: sqlite3.Connection):
    """清理 DB 中已不存在于 JSONL 的孤儿记录"""
    c = conn.cursor()

    jsonl_files = list(DATA_DIR.glob("*.jsonl"))
    if not jsonl_files:
        print("[PRUNE] 无 JSONL 文件，跳过")
        return

    # 收集所有 JSONL 中现有的 (source, title, content_hash)
    current_keys = set()
    for jsonl_file in jsonl_files:
        with open(jsonl_file, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                doc = json.loads(line)
                source = doc.get("source", "unknown")
                title = doc.get("title", "Untitled")
                content = doc.get("content", "")
                doc_hash = hashlib.md5(f"{source}:{title}:{content}".encode()).hexdigest()
                current_keys.add((source, title, doc_hash))

    # 获取 DB 中所有记录
    c.execute("SELECT id, source, title, content_hash FROM documents")
    db_rows = c.fetchall()

    orphaned_ids = []
    for row in db_rows:
        key = (row[1], row[2], row[3])
        if key not in current_keys:
            orphaned_ids.append(row[0])

    if not orphaned_ids:
        print("[PRUNE] 无孤儿记录")
        return

    # 分批删除
    batch_size = 500
    total_deleted = 0
    for i in range(0, len(orphaned_ids), batch_size):
        batch = orphaned_ids[i:i + batch_size]
        placeholders = ','.join('?' * len(batch))
        c.execute(f"DELETE FROM documents WHERE id IN ({placeholders})", batch)
        total_deleted += len(batch)
    conn.commit()

    print(f"[PRUNE] 已清理 {total_deleted} 条孤儿记录")


def migrate_database(conn: sqlite3.Connection):
    """迁移旧数据库：添加 content_hash 列并回填"""
    c = conn.cursor()

    # 检查 content_hash 列是否存在
    c.execute("PRAGMA table_info(documents)")
    columns = [row[1] for row in c.fetchall()]

    if "content_hash" not in columns:
        print("  [迁移] 添加 content_hash 列...")
        c.execute("ALTER TABLE documents ADD COLUMN content_hash TEXT")

        # 回填已有记录的 content_hash
        c.execute("SELECT id, source, title, content FROM documents")
        rows = c.fetchall()
        for row in rows:
            doc_hash = hashlib.md5(f"{row[1]}:{row[2]}:{row[3]}".encode()).hexdigest()
            c.execute("UPDATE documents SET content_hash = ? WHERE id = ?", (doc_hash, row[0]))
        conn.commit()
        print(f"  [迁移] 已回填 {len(rows)} 条记录的 content_hash")
    else:
        print("  [迁移] content_hash 列已存在，跳过")

def create_database():
    """创建 SQLite 数据库"""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            title TEXT,
            content TEXT NOT NULL,
            content_hash TEXT,
            embedding BLOB,
            metadata TEXT,
            UNIQUE(source, title, content_hash)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            source TEXT PRIMARY KEY,
            doc_count INTEGER DEFAULT 0,
            last_updated TEXT
        )
    """)
    conn.commit()
    return conn


def process_jsonl_files(conn: sqlite3.Connection, incremental: bool = True):
    """读取所有 JSONL 文件，分块并嵌入

    Args:
        conn: 数据库连接
        incremental: True=增量模式（跳过未变化文档），False=重建模式
    """
    c = conn.cursor()

    jsonl_files = list(DATA_DIR.glob("*.jsonl"))
    if not jsonl_files:
        print("[ERROR] 未找到 JSONL 文件，请先运行 preprocess.py", file=sys.stderr)
        return

    print(f"找到 {len(jsonl_files)} 个 JSONL 文件:")
    for f in jsonl_files:
        print(f"  - {f.name}")

    total_chunks = 0
    total_docs = 0
    total_skipped = 0

    for jsonl_file in jsonl_files:
        print(f"\n{'='*50}")
        print(f"处理: {jsonl_file.name}")
        print(f"{'='*50}")

        source_counts = {}

        with open(jsonl_file, encoding='utf-8') as f:
            docs = [json.loads(line) for line in f if line.strip()]

        print(f"  读取 {len(docs)} 个文档")

        # 增量模式：预加载已存在的 (source, title, content_hash)
        if incremental:
            existing_hashes = set()
            try:
                c.execute("SELECT source, title, content_hash FROM documents")
                for row in c.fetchall():
                    existing_hashes.add((row[0], row[1], row[2]))
                print(f"  已有 {len(existing_hashes)} 个文档记录（增量模式）")
            except Exception as e:
                print(f"  [WARN] 无法读取已有记录: {e}")
                existing_hashes = set()
        else:
            existing_hashes = set()

        # 分块
        all_chunks = []
        for doc in docs:
            source = doc.get("source", "unknown")
            title = doc.get("title", "Untitled")
            content = doc.get("content", "")
            metadata = doc.get("metadata", "{}")
            file_path = doc.get("file_path", "")

            doc_hash = hashlib.md5(f"{source}:{title}:{content}".encode()).hexdigest()

            # 代码文件整文件一块，手册分块
            if source == "example":
                if len(content) > CODE_MAX_CHARS:
                    chunks = [content[:CODE_MAX_CHARS]]
                else:
                    chunks = [content]
            else:
                chunks = chunk_text(content)

            for chunk in chunks:
                if len(chunk.strip()) < 20:
                    continue
                all_chunks.append({
                    "source": source,
                    "title": title,
                    "content": chunk,
                    "metadata": metadata,
                    "file_path": file_path,
                    "content_hash": doc_hash
                })

            source_counts[source] = source_counts.get(source, 0) + 1

        print(f"  分块后: {len(all_chunks)} 个块")

        # 批量嵌入并写入
        batch_write_size = 100
        for batch_start in range(0, len(all_chunks), batch_write_size):
            batch = all_chunks[batch_start:batch_start + batch_write_size]

            # 增量模式：过滤掉已存在的文档
            if incremental:
                new_batch = []
                for chunk in batch:
                    key = (chunk["source"], chunk["title"], chunk["content_hash"])
                    if key in existing_hashes:
                        total_skipped += 1
                        continue
                    new_batch.append(chunk)
                batch = new_batch

            if not batch:
                continue

            texts = [chunk["content"] for chunk in batch]

            embeddings = embed_texts_batch(texts)

            for chunk, emb in zip(batch, embeddings):
                if emb is None:
                    continue

                emb_blob = pickle.dumps(np.array(emb, dtype=np.float32))

                c.execute(
                    """
                    INSERT OR IGNORE INTO documents
                    (source, title, content, content_hash, embedding, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        chunk["source"],
                        chunk["title"],
                        chunk["content"],
                        chunk["content_hash"],
                        emb_blob,
                        chunk["metadata"],
                    ),
                )
                total_chunks += 1

            conn.commit()

            done = min(batch_start + batch_write_size, len(all_chunks))
            if incremental:
                print(
                    f"  进度: {done}/{len(all_chunks)} 块 "
                    f"(新增: {total_chunks}, 跳过: {total_skipped})",
                    file=sys.stderr,
                )
            else:
                print(f"  进度: {done}/{len(all_chunks)} 块已嵌入并存储", file=sys.stderr)

        total_docs += len(docs)

        for source, count in source_counts.items():
            c.execute("""
                INSERT OR REPLACE INTO sources (source, doc_count, last_updated)
                VALUES (?, ?, datetime('now'))
            """, (source, count))
        conn.commit()

    print(f"\n{'='*50}")
    print("构建完成!")
    print(f"  总文档数: {total_docs}")
    print(f"  新增块数: {total_chunks}")
    if incremental:
        print(f"  跳过块数: {total_skipped}")
    print(f"  数据库: {DB_PATH}")
    print(f"  数据库大小: {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"{'='*50}")


def main():
    parser = argparse.ArgumentParser(description="Geant4 RAG 向量索引构建")
    parser.add_argument(
        "--rebuild", action="store_true",
        help="删库重建，重新处理所有文档（默认是增量模式）"
    )
    parser.add_argument(
        "--skip-preprocess", action="store_true",
        help="跳过预处理步骤，仅对已有 JSONL 增量构建索引"
    )
    parser.add_argument(
        "--prune", action="store_true",
        help="清理 DB 中已不存在于 JSONL 的孤儿记录"
    )
    args = parser.parse_args()

    if args.rebuild:
        if DB_PATH.exists():
            DB_PATH.unlink()
            print(f"已删除旧数据库: {DB_PATH}")
        incremental = False
    else:
        incremental = True
        print("[增量模式] 只处理新增/变化的文档，跳过未变化的")
        print("  加上 --rebuild 参数可切换为删库重建模式")
        print()

    print("Geant4 RAG 向量索引构建")
    print(f"嵌入模型: {EMBED_MODEL}")
    print(f"块大小: ~{CHUNK_SIZE} tokens, 重叠: {CHUNK_OVERLAP} tokens")
    print()

    # 1. 预处理（除非明确跳过或重建）
    if not args.skip_preprocess:
        if args.rebuild:
            print("[预处理] 重建模式，运行完整 preprocess.py ...")
            result = subprocess.run(
                [sys.executable, str(PREPROCESS_SCRIPT)],
                capture_output=True, text=True, timeout=600
            )
            if result.stdout:
                print(result.stdout, end='')
            if result.stderr:
                print(result.stderr, end='', file=sys.stderr)
            # 重建后更新源文件缓存
            _save_source_cache(_scan_source_files())
        else:
            has_changes = run_preprocess()
            if not has_changes and not args.prune:
                print("\n源文件无变化，无需重建索引。使用 --rebuild 强制重建。")
                return
    else:
        print("[跳过预处理] 直接使用已有 JSONL 文件")

    conn = create_database()
    try:
        # 增量模式：先迁移旧数据库
        if incremental:
            migrate_database(conn)

        # 清理孤儿记录
        if args.prune:
            prune_orphaned_docs(conn)

        process_jsonl_files(conn, incremental=incremental)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
