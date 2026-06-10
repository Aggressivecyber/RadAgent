#!/usr/bin/env python3
"""
Geant4 文档预处理脚本
- HTML 文档 → Markdown（Application Developer Guide + Physics List Guide）
- 代码示例：每个示例取 example*.cc（主文件）+ include/*.hh（头文件）
- 输出 JSONL 格式到 data/ 目录
"""

import html.parser
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from knowledge_base.geant4.paths import geant4_example_root  # noqa: E402

BASE_DIR = Path(__file__).parent
RAW_DIR = BASE_DIR / "data" / "raw"
OUTPUT_DIR = BASE_DIR / "data"
OUTPUT_DIR.mkdir(exist_ok=True)

# HTML 文件所属的 source 分类
HTML_SOURCE_MAP = {
    "Analysis": "appdev", "Control": "appdev", "Detector": "appdev",
    "Examples": "appdev", "Fundamentals": "appdev", "GettingStarted": "appdev",
    "Introduction": "appdev", "LanguageBindings": "appdev", "UserActions": "appdev",
    "TrackingAndPhysics": "appdev", "Visualization": "appdev",
    "Appendix": "appdev", "Bibliography": "appdev",
    "electromagnetic": "physicslist", "hadronic": "physicslist",
    "reference_PL": "physicslist",
    # Toolkit Developer Guide
    "bftd_html": "toolkit",
    # Installation Guide
    "ig_html": "install",
    # Introduction
    "intro_html": "intro",
    # Physics List Guide (extended)
    "plg_html": "physicslist",
    # Physics Reference Manual
    "prm_html": "physicsref",
    # FAQ
    "faq_html": "faq",
}


# ============================================================================
# HTML → Markdown 转换器
# ============================================================================

class HTMLToMarkdown(html.parser.HTMLParser):
    """将 HTML 转为简化 Markdown，去除导航/CSS/JS"""

    SKIP_TAGS = {"nav", "footer", "script", "style", "noscript", "header"}
    BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
                  "li", "tr", "blockquote", "pre", "section", "article",
                  "table", "thead", "tbody", "dl", "dt", "dd"}
    SPACE_TAGS = {"br", "hr"}

    def __init__(self):
        super().__init__()
        self.result = []
        self.skip_depth = 0
        self.in_pre = False
        self.in_code = False
        self.list_depth = 0
        self.current_list_type = []
        self.list_counters = []
        self.skip_class = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_dict = dict(attrs)

        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return

        if self.skip_depth > 0:
            return

        if tag == "div":
            cls = attrs_dict.get("class", "")
            skip_classes = ["search", "navbar", "toolb", "navpat", "footer",
                          "header", "menu", "sidebar", "toc", "breadcrumb",
                          "copyright", "navigation", "sphinxsidebar",
                          "relations", "documentwrapper"]
            for sc in skip_classes:
                if sc in cls.lower():
                    self.skip_depth += 1
                    self.skip_class = True
                    return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            self.result.append("\n" + "#" * level + " ")
        elif tag == "p":
            self.result.append("\n\n")
        elif tag == "br":
            self.result.append("\n")
        elif tag == "hr":
            self.result.append("\n---\n")
        elif tag == "pre":
            self.in_pre = True
            self.result.append("\n```\n")
        elif tag == "code":
            self.in_code = True
        elif tag in ("em", "i"):
            self.result.append("*")
        elif tag in ("strong", "b"):
            self.result.append("**")
        elif tag == "ul":
            self.current_list_type.append("ul")
            self.list_counters.append(0)
            self.list_depth += 1
            self.result.append("\n")
        elif tag == "ol":
            self.current_list_type.append("ol")
            self.list_counters.append(0)
            self.list_depth += 1
            self.result.append("\n")
        elif tag == "li":
            if self.list_depth > 0 and len(self.current_list_type) > 0:
                indent = "  " * (self.list_depth - 1)
                if self.current_list_type[-1] == "ul":
                    self.result.append(f"\n{indent}- ")
                else:
                    self.list_counters[-1] += 1
                    self.result.append(f"\n{indent}{self.list_counters[-1]}. ")
        elif tag in ("td", "th"):
            self.result.append(" | ")
    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in self.SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return

        if self.skip_depth > 0:
            if self.skip_class and tag == "div":
                self.skip_depth = max(0, self.skip_depth - 1)
                self.skip_class = False
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.result.append("\n")
        elif tag == "p":
            self.result.append("\n")
        elif tag == "pre":
            self.in_pre = False
            self.result.append("\n```\n")
        elif tag == "code":
            self.in_code = False
        elif tag in ("em", "i"):
            self.result.append("*")
        elif tag in ("strong", "b"):
            self.result.append("**")
        elif tag in ("ul", "ol"):
            if self.list_depth > 0:
                self.list_depth -= 1
                if self.current_list_type:
                    self.current_list_type.pop()
                if self.list_counters:
                    self.list_counters.pop()
            self.result.append("\n")
        elif tag == "table":
            self.result.append("\n")
        elif tag == "tr":
            self.result.append("\n")

    def handle_data(self, data):
        if self.skip_depth > 0:
            return
        if self.in_pre:
            self.result.append(data)
        else:
            text = re.sub(r'\s+', ' ', data)
            self.result.append(text)

    def handle_entityref(self, name):
        if self.skip_depth > 0:
            return
        entities = {"lt": "<", "gt": ">", "amp": "&", "quot": '"',
                    "apos": "'", "nbsp": " ", "copy": "(c)", "reg": "(R)"}
        self.result.append(entities.get(name, f"&{name};"))

    def handle_charref(self, name):
        if self.skip_depth > 0:
            return
        try:
            if name.startswith("x"):
                char = chr(int(name[1:], 16))
            else:
                char = chr(int(name))
            self.result.append(char)
        except (ValueError, OverflowError):
            self.result.append(f"&#{name};")

    def get_markdown(self):
        text = "".join(self.result)
        text = re.sub(r'\n{3,}', '\n\n', text)
        lines = [line.strip() for line in text.split('\n')]
        return '\n'.join(lines).strip()


def html_to_markdown(html_content: str) -> str:
    """将 HTML 内容转为 Markdown"""
    parser = HTMLToMarkdown()
    try:
        parser.feed(html_content)
        return parser.get_markdown()
    except Exception:
        text = re.sub(r'<[^>]+>', ' ', html_content)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()


def extract_html_title(html_content: str) -> str:
    """从 HTML 中提取标题"""
    m = re.search(r'<title>(.*?)</title>', html_content, re.IGNORECASE | re.DOTALL)
    if m:
        title = m.group(1).strip()
        title = re.sub(r'<[^>]+>', '', title)
        title = re.sub(r'\s+', ' ', title)
        # 清理 "Geant4 ..." 等前缀
        title = re.sub(r'^Geant4\s*', '', title)
        return title[:200]
    # 尝试从 h1 提取
    m = re.search(r'<h[1][^>]*>(.*?)</h1>', html_content, re.IGNORECASE | re.DOTALL)
    if m:
        title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        return title[:200]
    return "Untitled"


# ============================================================================
# HTML 文档处理
# ============================================================================

def process_html_file(filepath: str, source_type: str) -> dict | None:
    """处理单个 HTML 文件"""
    try:
        with open(filepath, encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"  [WARN] 读取失败 {filepath}: {e}", file=sys.stderr)
        return None

    title = extract_html_title(content)
    markdown = html_to_markdown(content)

    if len(markdown) < 50:
        return None

    rel_path = os.path.relpath(filepath, str(RAW_DIR))

    return {
        "source": source_type,
        "file_path": filepath,
        "title": title,
        "content": markdown,
        "metadata": json.dumps({
            "type": source_type,
            "file": os.path.basename(filepath),
            "path": rel_path,
            "format": "html"
        }, ensure_ascii=False)
    }


def process_all_html() -> int:
    """处理所有 HTML 文档"""
    count = 0
    html_files = sorted(RAW_DIR.rglob("*.html"))
    print(f"\n[HTML] 找到 {len(html_files)} 个 HTML 文件")

    for html_file in html_files:
        rel = html_file.relative_to(RAW_DIR)
        rel_str = str(rel)
        # 确定 source 类型（先匹配顶级目录，再匹配路径中的关键子目录）
        top_dir = rel_str.split('/')[0] if '/' in rel_str else ''
        source = HTML_SOURCE_MAP.get(top_dir)
        if not source:
            # 匹配路径中的文档集名称
            for key, val in HTML_SOURCE_MAP.items():
                if f'/{key}/' in rel_str or rel_str.startswith(f'{key}/'):
                    source = val
                    break
        if not source:
            source = "appdev"

        doc = process_html_file(str(html_file), source)
        if doc and doc["content"]:
            yield doc
            count += 1

    print(f"[HTML] 完成: {count} 个文档")


# ============================================================================
# 代码示例处理
# ============================================================================

def extract_cc_description(filepath: str) -> str:
    """从 .cc 文件提取头部注释描述"""
    try:
        with open(filepath, encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception:
        return ""

    comments = []
    in_block_comment = False
    for line in lines[:30]:
        stripped = line.strip()
        if stripped.startswith('/*'):
            in_block_comment = True
            stripped = stripped[2:].strip()
        if in_block_comment:
            if '*/' in stripped:
                in_block_comment = False
                stripped = stripped.replace('*/', '').strip()
            else:
                stripped = stripped.lstrip('*').strip()
            if stripped and not stripped.startswith('!') and len(stripped) > 5:
                comments.append(stripped)
        elif stripped.startswith('//'):
            text = stripped[2:].strip()
            if text and len(text) > 5:
                comments.append(text)

    return ' '.join(comments[:3])


def process_example(example_dir: str, category: str, subcategory: str = "") -> list[dict]:
    """处理单个示例目录，取 main .cc + include/*.hh"""
    docs = []
    example_name = os.path.basename(example_dir)

    # 构建标题前缀
    if subcategory:
        title_prefix = f"{category}/{subcategory}/{example_name}"
    else:
        title_prefix = f"{category}/{example_name}"

    # 查找 main .cc 文件（example*.cc 或项目同名 .cc）
    main_cc = None
    include_dir = os.path.join(example_dir, "include")

    # 优先查找 example*.cc
    for fname in sorted(os.listdir(example_dir)):
        if fname.endswith('.cc') and (
            fname.startswith('example') or fname.startswith(example_name)
        ):
            main_cc = os.path.join(example_dir, fname)
            break

    # 查找 include/*.hh
    header_files = []
    if os.path.isdir(include_dir):
        for fname in sorted(os.listdir(include_dir)):
            if fname.endswith('.hh'):
                header_files.append(os.path.join(include_dir, fname))

    # 处理 main .cc
    if main_cc:
        doc = _make_code_doc(main_cc, title_prefix, category, subcategory, example_name, "main")
        if doc:
            docs.append(doc)

    # 处理 include/*.hh（头文件通常包含类定义，信息密度高）
    for hh_path in header_files:
        doc = _make_code_doc(hh_path, title_prefix, category, subcategory, example_name, "header")
        if doc:
            docs.append(doc)

    return docs


def _make_code_doc(filepath: str, title_prefix: str, category: str,
                   subcategory: str, example_name: str, role: str) -> dict | None:
    """生成单个代码文件的文档"""
    try:
        with open(filepath, encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return None

    if len(content.strip()) < 20:
        return None

    # 截断超长文件
    if len(content) > 8000:
        content = content[:8000]

    description = extract_cc_description(filepath)
    basename = os.path.basename(filepath)
    title = f"{title_prefix} - {basename}"
    if description and len(description) < 100:
        title += f" ({description})"

    # 推断涉及的 Geant4 类
    g4_classes = set()
    for match in re.finditer(r'\b(G4\w+)\b', content):
        cls = match.group(1)
        if len(cls) > 4 and len(cls) < 40:
            g4_classes.add(cls)
    g4_list = sorted(g4_classes)[:10]

    # 推断涉及的功能
    features = []
    feature_patterns = [
        (r'G4VUserDetectorConstruction', "Detector Construction"),
        (r'G4VUserPhysicsList|G4VModularPhysicsList', "Physics List"),
        (r'G4VUserPrimaryGeneratorAction', "Primary Generator"),
        (r'G4UserEventAction', "Event Action"),
        (r'G4UserRunAction', "Run Action"),
        (r'G4UserSteppingAction', "Stepping Action"),
        (r'G4UserTrackingAction', "Tracking Action"),
        (r'G4UserStackingAction', "Stacking Action"),
        (r'G4VSensitiveDetector', "Sensitive Detector"),
        (r'G4VSolid|G4Box|G4Tubs|G4Sphere|G4Cons', "Geometry/Solids"),
        (r'G4LogicalVolume|G4VPhysicalVolume', "Volume"),
        (r'G4Material|G4NistManager', "Material"),
        (r'G4EmStandardPhysics|G4EmLivermorePhysics|G4EmPenelopePhysics', "EM Physics"),
        (r'G4HadronicProcessStore|FTFP|QGSP', "Hadronic Physics"),
        (r'G4ScoringManager|G4ScoringBox', "Scoring"),
        (r'G4AnalysisManager', "Analysis/Histogram"),
        (r'G4UIsession|G4UImanager', "UI/Command"),
        (r'G4VisManager', "Visualization"),
    ]
    for pattern, feature in feature_patterns:
        if re.search(pattern, content):
            features.append(feature)

    content_parts = []
    if description:
        content_parts.append(f"# {description}")
    if features:
        content_parts.append(f"Features: {', '.join(features)}")
    if g4_list:
        content_parts.append(f"Classes: {', '.join(g4_list)}")
    content_parts.append(f"Category: {category}")
    if subcategory:
        content_parts.append(f"Subcategory: {subcategory}")
    content_parts.append(f"Example: {example_name}")
    content_parts.append(f"File: {basename} ({role})")
    content_parts.append("")
    content_parts.append("```cpp")
    content_parts.append(content)
    content_parts.append("```")

    full_content = '\n'.join(content_parts)

    return {
        "source": "example",
        "file_path": filepath,
        "title": title,
        "content": full_content,
        "metadata": json.dumps({
            "type": "example",
            "category": category,
            "subcategory": subcategory,
            "example": example_name,
            "file": basename,
            "role": role,
            "format": "cpp",
            "features": features,
            "g4_classes": g4_list
        }, ensure_ascii=False)
    }


def process_all_examples():
    """处理所有代码示例"""
    count = 0
    examples_dir = geant4_example_root()
    if examples_dir is None:
        print(
            "[SKIP] 示例目录不存在。设置 RADAGENT_GEANT4_EXAMPLES_ROOT 指向 Geant4 examples。",
            file=sys.stderr,
        )
        return

    print(f"\n[EXAMPLES] 处理示例目录: {examples_dir}")

    # basic/ 目录：每个子目录是一个示例
    basic_dir = examples_dir / "basic"
    if basic_dir.exists():
        for example_dir in sorted(basic_dir.iterdir()):
            if not example_dir.is_dir():
                continue
            for doc in process_example(str(example_dir), "basic"):
                yield doc
                count += 1

    # extended/ 目录：两级子目录 category/subcategory/example
    extended_dir = examples_dir / "extended"
    if extended_dir.exists():
        for cat_dir in sorted(extended_dir.iterdir()):
            if not cat_dir.is_dir():
                continue
            category = cat_dir.name

            # 检查是否有子目录（有些直接就是示例）
            has_sub_examples = False
            sub_items = sorted(cat_dir.iterdir())
            for sub in sub_items:
                if not sub.is_dir():
                    continue
                # 如果子目录包含 .cc 文件或 include/ 目录，它本身是一个示例
                has_cc = any(f.suffix == '.cc' for f in sub.iterdir() if f.is_file())
                has_include = (sub / "include").is_dir()
                has_src = (sub / "src").is_dir()

                if has_cc or has_include or has_src:
                    has_sub_examples = True
                    for doc in process_example(str(sub), "extended", category):
                        yield doc
                        count += 1
                    if count % 50 == 0:
                        print(f"  已处理 {count} 个代码文件...", file=sys.stderr)

            # 如果没有子示例，cat_dir 本身可能是一个示例
            if not has_sub_examples:
                cc_files = list(cat_dir.glob("*.cc"))
                if cc_files:
                    for doc in process_example(str(cat_dir), "extended", ""):
                        yield doc
                        count += 1

    # advanced/ 目录
    advanced_dir = examples_dir / "advanced"
    if advanced_dir.exists():
        for example_dir in sorted(advanced_dir.iterdir()):
            if not example_dir.is_dir():
                continue
            for doc in process_example(str(example_dir), "advanced"):
                yield doc
                count += 1

    print(f"[EXAMPLES] 完成: {count} 个文档")


# ============================================================================
# 主流程
# ============================================================================

def main():
    print("=" * 60)
    print("Geant4 文档预处理")
    print("=" * 60)

    manuals_output = OUTPUT_DIR / "manuals.jsonl"
    examples_output = OUTPUT_DIR / "examples.jsonl"

    # 1. 处理 HTML 文档
    html_count = 0
    with open(manuals_output, 'w', encoding='utf-8') as out:
        for doc in process_all_html():
            out.write(json.dumps(doc, ensure_ascii=False) + '\n')
            html_count += 1

    # 2. 处理代码示例
    example_count = 0
    with open(examples_output, 'w', encoding='utf-8') as out:
        for doc in process_all_examples():
            out.write(json.dumps(doc, ensure_ascii=False) + '\n')
            example_count += 1

    print(f"\n{'='*60}")
    print(
        f"总计: {html_count} HTML 文档 + {example_count} 代码示例 = "
        f"{html_count + example_count} 文档"
    )
    print("输出:")
    print(f"  - {manuals_output} ({html_count} docs)")
    print(f"  - {examples_output} ({example_count} docs)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
