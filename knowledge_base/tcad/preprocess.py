#!/usr/bin/env python3
"""
TCAD 文档预处理脚本
- 将 HTML 手册转为 Markdown（去除 CSS/JS/导航/footer，保留正文）
- 为 .cmd/.tcl 代码文件生成上下文描述
- 输出 JSONL 格式到 data/ 目录
"""

import html.parser
import json
import os
import re
import sys
from pathlib import Path

TCAD_ROOT = os.environ.get("RADAGENT_TCAD_ROOT") or os.environ.get("TCAD_ROOT", "")
OUTPUT_DIR = Path(__file__).parent / "data"
OUTPUT_DIR.mkdir(exist_ok=True)


# ============================================================================
# HTML -> Markdown 转换器（纯标准库，不依赖 bs4）
# ============================================================================

class HTMLToMarkdown(html.parser.HTMLParser):
    """将 HTML 转为简化 Markdown，去除导航/CSS/JS"""

    # 需要跳过的标签（导航栏、页脚、脚本、样式）
    SKIP_TAGS = {"nav", "footer", "script", "style", "noscript", "header"}
    # 块级元素（前后加换行）
    BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
                  "li", "tr", "blockquote", "pre", "section", "article",
                  "table", "thead", "tbody", "dl", "dt", "dd"}
    # 行内需要空格分隔的标签
    SPACE_TAGS = {"br", "hr"}

    def __init__(self):
        super().__init__()
        self.result = []
        self.skip_depth = 0  # 当前跳过的嵌套深度
        self.in_pre = False
        self.in_code = False
        self.list_depth = 0
        self.current_list_type = []  # 'ul' or 'ol'
        self.list_counters = []
        self.skip_class = False  # 跳过特定 class 的 div

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_dict = dict(attrs)

        # 跳过导航/页脚区域
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return

        if self.skip_depth > 0:
            return

        # 跳过包含特定 class 的 div（如搜索栏、工具栏）
        if tag == "div":
            cls = attrs_dict.get("class", "")
            skip_classes = ["wh_search_input", "wh_header", "wh_footer",
                          "wh_publication_title", "wh_logo", "wh_top_menu",
                          "wh_child_links", "wh_related_links",
                          "wh_copyright", "wh_breadcrumb",
                          "search", "navbar", "toolb", "navpat"]
            for sc in skip_classes:
                if sc in cls:
                    self.skip_depth += 1
                    self.skip_class = True
                    return

        # 处理标题
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
        elif tag == "em" or tag == "i":
            self.result.append("*")
        elif tag == "strong" or tag == "b":
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
        elif tag == "table":
            self.result.append("\n")
        elif tag == "td" or tag == "th":
            self.result.append(" | ")
        elif tag in ("img", "image"):
            alt = attrs_dict.get("alt", "")
            self.result.append(f"[Image: {alt}]")

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
        elif tag == "em" or tag == "i":
            self.result.append("*")
        elif tag == "strong" or tag == "b":
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
            # 压缩空白但保留单个空格
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
        # 清理多余空行（最多保留两个连续换行）
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 清理行首尾空格
        lines = [line.strip() for line in text.split('\n')]
        return '\n'.join(lines).strip()


def html_to_markdown(html_content: str) -> str:
    """将 HTML 内容转为 Markdown"""
    parser = HTMLToMarkdown()
    try:
        parser.feed(html_content)
        return parser.get_markdown()
    except Exception:
        # 解析失败时简单去除标签
        text = re.sub(r'<[^>]+>', ' ', html_content)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()


# ============================================================================
# 文档处理函数
# ============================================================================

def extract_html_title(html_content: str) -> str:
    """从 HTML 中提取标题"""
    m = re.search(r'<title>(.*?)</title>', html_content, re.IGNORECASE | re.DOTALL)
    if m:
        title = m.group(1).strip()
        # 去除 HTML 实体和多余文字
        title = re.sub(r'<[^>]+>', '', title)
        title = re.sub(r'\s+', ' ', title)
        return title[:200]
    return "Untitled"


def process_html_file(filepath: str, source_type: str) -> dict | None:
    """处理单个 HTML 文件，返回文档记录"""
    try:
        with open(filepath, encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"  [WARN] 读取失败 {filepath}: {e}", file=sys.stderr)
        return None

    title = extract_html_title(content)
    markdown = html_to_markdown(content)

    # 跳过内容太短的页面（导航页、空页）
    if len(markdown) < 50:
        return None

    return {
        "source": source_type,
        "file_path": filepath,
        "title": title,
        "content": markdown,
        "metadata": json.dumps({
            "type": source_type,
            "file": os.path.relpath(filepath, TCAD_ROOT),
            "format": "html"
        })
    }


def process_code_file(filepath: str, category: str) -> dict | None:
    """处理 .cmd/.tcl 代码文件，生成上下文描述"""
    try:
        with open(filepath, encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  [WARN] 读取失败 {filepath}: {e}", file=sys.stderr)
        return None

    if not lines:
        return None

    # 提取文件前 30 行的注释作为描述
    comment_lines = []
    for line in lines[:30]:
        stripped = line.strip()
        if stripped.startswith('#') or stripped.startswith('//'):
            comment_lines.append(stripped.lstrip('#/ ').strip())
        elif stripped and not stripped.startswith('#'):
            break  # 注释块结束

    description = ' '.join(comment_lines) if comment_lines else ""

    # 从目录路径推断用途
    rel_path = os.path.relpath(filepath, TCAD_ROOT)
    parts = rel_path.split(os.sep)

    # 提取工具类型（从文件扩展名和命名）
    basename = os.path.basename(filepath)
    name_no_ext = os.path.splitext(basename)[0]

    # 推断使用的工具
    tool_hints = []
    if 'sprocess' in name_no_ext or 'fps' in name_no_ext:
        tool_hints.append("Sentaurus Process")
    if 'sdevice' in name_no_ext or '_des' in name_no_ext:
        tool_hints.append("Sentaurus Device")
    if 'svisual' in name_no_ext or '_vis' in name_no_ext:
        tool_hints.append("Sentaurus Visual")
    if 'sde' in name_no_ext.split('_'):
        tool_hints.append("Sentaurus Structure Editor")
    if 'sworkbench' in name_no_ext or 'swb' in name_no_ext:
        tool_hints.append("Sentaurus Workbench")

    # 构建内容：描述 + 完整代码
    content_parts = []
    if description:
        content_parts.append(f"# {description}")
    if tool_hints:
        content_parts.append(f"Tools: {', '.join(tool_hints)}")
    content_parts.append(f"Category: {category}")
    content_parts.append(f"File: {rel_path}")
    content_parts.append("")
    content_parts.append("```")
    content_parts.extend(line.rstrip() for line in lines)
    content_parts.append("```")

    content = '\n'.join(content_parts)

    # 标题：类别 + 项目名 + 文件名
    project_name = parts[-2] if len(parts) >= 2 else ""
    title_parts = [category]
    if project_name and project_name != "Applications_Library":
        title_parts.append(project_name)
    title_parts.append(basename)
    title = " - ".join(title_parts)

    return {
        "source": "code",
        "file_path": filepath,
        "title": title,
        "content": content,
        "metadata": json.dumps({
            "type": "code",
            "category": category,
            "file": rel_path,
            "format": os.path.splitext(filepath)[1],
            "tools": tool_hints
        })
    }


# ============================================================================
# 主处理流程
# ============================================================================

def process_manuals(output_file: str, subdirs: list[str] | None = None):
    """处理 HTML 手册目录"""
    manuals_dir = os.path.join(TCAD_ROOT, "manuals")

    if subdirs:
        dirs_to_process = [os.path.join(manuals_dir, d) for d in subdirs]
    else:
        dirs_to_process = [manuals_dir]

    count = 0
    with open(output_file, 'w', encoding='utf-8') as out:
        for base_dir in dirs_to_process:
            if not os.path.exists(base_dir):
                print(f"[SKIP] 目录不存在: {base_dir}", file=sys.stderr)
                continue

            # 确定源类型
            source_type = os.path.relpath(base_dir, manuals_dir).split(os.sep)[0]
            print(f"[HTML] 处理目录: {base_dir}")

            for root, dirs, files in os.walk(base_dir):
                for fname in files:
                    if not fname.endswith('.html'):
                        continue

                    filepath = os.path.join(root, fname)
                    doc = process_html_file(filepath, source_type)
                    if doc and doc["content"]:
                        out.write(json.dumps(doc, ensure_ascii=False) + '\n')
                        count += 1
                        if count % 100 == 0:
                            print(f"  已处理 {count} 个 HTML 文件...", file=sys.stderr)

    print(f"[HTML] 完成: {count} 个文档 -> {output_file}")
    return count


def process_applications(output_file: str):
    """处理 Applications_Library 代码文件"""
    app_dir = os.path.join(TCAD_ROOT, "Applications_Library")

    if not os.path.exists(app_dir):
        print(f"[SKIP] 目录不存在: {app_dir}", file=sys.stderr)
        return 0

    count = 0
    with open(output_file, 'w', encoding='utf-8') as out:
        for root, dirs, files in os.walk(app_dir):
            for fname in files:
                if not (fname.endswith('.cmd') or fname.endswith('.tcl')):
                    continue

                filepath = os.path.join(root, fname)

                # 从路径提取类别（如 FinFET, CMOS 等）
                rel = os.path.relpath(filepath, app_dir)
                category = rel.split(os.sep)[0]

                doc = process_code_file(filepath, category)
                if doc and doc["content"]:
                    out.write(json.dumps(doc, ensure_ascii=False) + '\n')
                    count += 1
                    if count % 200 == 0:
                        print(f"  已处理 {count} 个代码文件...", file=sys.stderr)

    print(f"[CODE] 完成: {count} 个文档 -> {output_file}")
    return count


def main():
    # 只处理 olh_sentaurus + Applications_Library 做测试
    print("=" * 60)
    print("TCAD 文档预处理")
    print("=" * 60)
    if not TCAD_ROOT:
        print(
            "[ERROR] 请设置 RADAGENT_TCAD_ROOT 或 TCAD_ROOT 指向 Sentaurus TCAD 根目录",
            file=sys.stderr,
        )
        sys.exit(1)

    # 1. 处理 olh_sentaurus 手册
    html_output = str(OUTPUT_DIR / "manuals.jsonl")
    html_count = process_manuals(html_output, subdirs=["olh_sentaurus"])

    # 2. 处理 Applications_Library 代码
    code_output = str(OUTPUT_DIR / "applications.jsonl")
    code_count = process_applications(code_output)

    print("=" * 60)
    print(f"总计: {html_count} HTML + {code_count} 代码 = {html_count + code_count} 个文档")
    print(f"输出目录: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
