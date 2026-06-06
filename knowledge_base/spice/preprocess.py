#!/usr/bin/env python3
"""
ngspice 文档预处理脚本
- 解析 Texinfo 手册（ngspice.texi）→ Markdown
- HTML 教程/文档 → Markdown
- 电路示例代码（.cir/.sp/.net/.mod/.lib 等）→ 带描述的文档
- 输出 JSONL 格式到 data/ 目录
"""

import html.parser
import json
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
RAW_DIR = BASE_DIR / "data" / "raw"
EXAMPLES_DIR = "/tmp/ngspice-46/examples"
OUTPUT_DIR = BASE_DIR / "data"
OUTPUT_DIR.mkdir(exist_ok=True)


# ============================================================================
# Texinfo → Markdown 转换器
# ============================================================================

def texi_to_markdown(texi_content: str) -> str:
    """将 Texinfo 格式转为 Markdown"""
    lines = texi_content.split('\n')
    result = []
    in_block = False
    block_type = ""
    skip_node = False
    current_chapter = ""

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 跳过条件编译指令
        if stripped.startswith('@if') or stripped.startswith('@end if'):
            i += 1
            continue

        # 跳过 @ignore ... @end ignore 块
        if stripped == '@ignore':
            while i < len(lines) and lines[i].strip() != '@end ignore':
                i += 1
            i += 1
            continue

        # 跳过 @tex ... @end tex 块
        if stripped == '@tex':
            while i < len(lines) and lines[i].strip() != '@end tex':
                i += 1
            i += 1
            continue

        # 跳过 @html ... @end html 块
        if stripped == '@html':
            while i < len(lines) and lines[i].strip() != '@end html':
                i += 1
            i += 1
            continue

        # 跳过 @format / @display 块中的索引条目
        if stripped in ('@format', '@display'):
            in_block = True
            block_type = stripped
            i += 1
            continue
        if in_block and stripped == f'@end {block_type[1:]}':
            in_block = False
            i += 1
            continue

        # 处理章节标题
        if stripped.startswith('@chapter '):
            title = _clean_texi(stripped[9:])
            current_chapter = title
            result.append(f"\n# {title}\n")
        elif stripped.startswith('@section '):
            title = _clean_texi(stripped[9:])
            result.append(f"\n## {title}\n")
        elif stripped.startswith('@subsection '):
            title = _clean_texi(stripped[12:])
            result.append(f"\n### {title}\n")
        elif stripped.startswith('@subsubsection '):
            title = _clean_texi(stripped[15:])
            result.append(f"\n#### {title}\n")
        elif stripped.startswith('@appendix '):
            title = _clean_texi(stripped[10:])
            result.append(f"\n# Appendix: {title}\n")
        elif stripped.startswith('@appendixsec '):
            title = _clean_texi(stripped[13:])
            result.append(f"\n## {title}\n")
        elif stripped.startswith('@unnumbered '):
            title = _clean_texi(stripped[12:])
            result.append(f"\n# {title}\n")

        # 处理 @node（Texinfo 导航节点，跳过）
        elif stripped.startswith('@node '):
            pass

        # 处理 @menu（目录菜单，跳过）
        elif stripped.startswith('@menu'):
            while i < len(lines) and lines[i].strip() != '@end menu':
                i += 1

        # 处理 @itemize / @enumerate 列表
        elif stripped.startswith('@itemize'):
            pass
        elif stripped.startswith('@enumerate'):
            pass
        elif stripped.startswith('@end itemize') or stripped.startswith('@end enumerate'):
            pass
        elif stripped == '@item' or stripped.startswith('@item '):
            item_text = stripped[5:].strip() if len(stripped) > 5 else ""
            result.append(f"\n- {_clean_texi(item_text)}")

        # 处理 @deffn / @defvr 等函数/变量定义
        elif stripped.startswith('@deffn ') or stripped.startswith('@defvr ') or \
             stripped.startswith('@deftp ') or stripped.startswith('@deftypefn '):
            defn = _clean_texi(stripped)
            result.append(f"\n**{_clean_texi(stripped.split(None, 1)[1] if ' ' in stripped else '')}**\n")
        elif stripped.startswith('@end deffn') or stripped.startswith('@end defvr') or \
             stripped.startswith('@end deftp') or stripped.startswith('@end deftypefn'):
            pass

        # 处理 @example / @smallexample 代码块
        elif stripped in ('@example', '@smallexample', '@lisp'):
            result.append("\n```\n")
            i += 1
            # 收集代码块内容
            end_tags = ('@end example', '@end smallexample', '@end lisp')
            while i < len(lines):
                eline = lines[i].strip()
                if eline in end_tags:
                    break
                result.append(_clean_texi_line(lines[i].rstrip()))
                i += 1
            result.append("\n```\n")

        # 处理 @table
        elif stripped.startswith('@table '):
            pass
        elif stripped.startswith('@end table'):
            pass

        # 处理 @multitable
        elif stripped.startswith('@multitable'):
            pass
        elif stripped.startswith('@end multitable'):
            pass
        elif stripped.startswith('@item ') and not in_block:
            pass

        # 处理 @quotation
        elif stripped == '@quotation':
            result.append("\n> ")
        elif stripped == '@end quotation':
            result.append("\n")

        # 处理 @copying（跳过版权声明）
        elif stripped == '@copying':
            while i < len(lines) and lines[i].strip() != '@end copying':
                i += 1

        # 处理 @titlepage（跳过）
        elif stripped == '@titlepage':
            while i < len(lines) and lines[i].strip() != '@end titlepage':
                i += 1

        # 处理 @c / @comment（注释，跳过）
        elif stripped.startswith('@c ') or stripped.startswith('@comment '):
            pass

        # 处理 @set / @clear 等指令
        elif stripped.startswith('@set ') or stripped.startswith('@clear ') or \
             stripped.startswith('@setfilename') or stripped.startswith('@settitle') or \
             stripped.startswith('@setchapternewpage') or stripped.startswith('@include '):
            pass

        # 处理 @center / @sp 等排版
        elif stripped.startswith('@center '):
            text = _clean_texi(stripped[8:])
            if text:
                result.append(f"\n{text}\n")
        elif stripped.startswith('@sp '):
            result.append("\n")

        # 处理 @ref / @xref / @pxref 交叉引用
        elif stripped.startswith('@xref{') or stripped.startswith('@ref{') or stripped.startswith('@pxref{'):
            ref_text = _clean_texi(stripped)
            result.append(ref_text)

        # 处理 @uref URL引用
        elif '@uref{' in stripped:
            line_text = _clean_texi(stripped)
            result.append(line_text)

        # 普通文本行
        elif stripped and not stripped.startswith('@'):
            cleaned = _clean_texi(stripped)
            if cleaned:
                result.append(cleaned)

        # 以 @ 开头但未特殊处理的行
        elif stripped.startswith('@') and not stripped.startswith('@end'):
            cleaned = _clean_texi(stripped)
            if cleaned and not cleaned.startswith('@'):
                result.append(cleaned)

        i += 1

    text = '\n'.join(result)
    # 清理多余空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _clean_texi(text: str) -> str:
    """清理 Texinfo 格式标记"""
    if not text:
        return ""
    # 移除 @code{...} → 保留内容加反引号
    text = re.sub(r'@code\{([^}]*)\}', r'`\1`', text)
    # 移除 @emph{...} → *...*
    text = re.sub(r'@emph\{([^}]*)\}', r'*\1*', text)
    # 移除 @strong{...} → **...**
    text = re.sub(r'@strong\{([^}]*)\}', r'**\1**', text)
    # 移除 @var{...} → *...*
    text = re.sub(r'@var\{([^}]*)\}', r'*\1*', text)
    # 移除 @file{...} → `...`
    text = re.sub(r'@file\{([^}]*)\}', r'`\1`', text)
    # 移除 @command{...} → `...`
    text = re.sub(r'@command\{([^}]*)\}', r'`\1`', text)
    # 移除 @option{...} → `...`
    text = re.sub(r'@option\{([^}]*)\}', r'`\1`', text)
    # 移除 @env{...} → `...`
    text = re.sub(r'@env\{([^}]*)\}', r'`\1`', text)
    # 移除 @samp{...} → `...`
    text = re.sub(r'@samp\{([^}]*)\}', r'`\1`', text)
    # 移除 @key{...} → <...>
    text = re.sub(r'@key\{([^}]*)\}', r'<\1>', text)
    # 移除 @url{...}
    text = re.sub(r'@url\{([^}]*)\}', r'\1', text)
    # 移除 @uref{url, text} → text (url)
    text = re.sub(r'@uref\{([^,]*),\s*([^}]*)\}', r'\2 (\1)', text)
    text = re.sub(r'@uref\{([^}]*)\}', r'\1', text)
    # 移除 @xref{node} / @ref{node} / @pxref{node} → "see node"
    text = re.sub(r'@pxref\{([^}]*)\}', r'see \1', text)
    text = re.sub(r'@xref\{([^}]*)\}', r'See \1', text)
    text = re.sub(r'@ref\{([^}]*)\}', r'\1', text)
    # 移除 @anchor{...}
    text = re.sub(r'@anchor\{[^}]*\}', '', text)
    # 移除 @footnote{...} → (...)
    text = re.sub(r'@footnote\{([^}]*)\}', r'(\1)', text)
    # 移除 @caption{...}
    text = re.sub(r'@caption\{([^}]*)\}', r'\1', text)
    # 移除 @cite{...} → "...'"
    text = re.sub(r'@cite\{([^}]*)\}', r"'\1'", text)
    # 移除 @dfn{...} → "..."
    text = re.sub(r'@dfn\{([^}]*)\}', r'"\1"', text)
    # 移除 @math{...}
    text = re.sub(r'@math\{([^}]*)\}', r'\1', text)
    # 移除 @tex / @end tex 内嵌公式
    text = re.sub(r'@tex[^@]*@end tex', '', text)
    # 移除 @w{...} (保持空格)
    text = re.sub(r'@w\{([^}]*)\}', r'\1', text)
    # 移除 @t{...} → `...`
    text = re.sub(r'@t\{([^}]*)\}', r'`\1`', text)
    # 移除 @asis{...}
    text = re.sub(r'@asis\{([^}]*)\}', r'\1', text)
    # 移除 @result{} → =>
    text = re.sub(r'@result\{\}', '=>', text)
    # 移除 @bullet{} → *
    text = re.sub(r'@bullet\{\}', '*', text)
    # 移除 @dots{} → ...
    text = re.sub(r'@dots\{\}', '...', text)
    # 移除 @equiv{} → ≡
    text = re.sub(r'@equiv\{\}', '≡', text)
    # 移除 @point{} → -
    text = re.sub(r'@point\{\}', '-', text)
    # 移除 @error{} → error-->
    text = re.sub(r'@error\{\}', 'error-->', text)
    # 移除 @print{} → -|
    text = re.sub(r'@print\{\}', '-|', text)
    # 清理剩余的 @xxx{...}
    text = re.sub(r'@\w+\{([^}]*)\}', r'\1', text)
    # 清理独立的 @ 指令
    text = re.sub(r'@\w+', '', text)
    # 清理花括号
    text = text.replace('{', '').replace('}', '')
    # 压缩空白
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _clean_texi_line(line: str) -> str:
    """清理单行 Texinfo（保留缩进，用于代码块）"""
    # 只处理内联标记
    line = re.sub(r'@code\{([^}]*)\}', r'\1', line)
    line = re.sub(r'@var\{([^}]*)\}', r'\1', line)
    line = re.sub(r'@emph\{([^}]*)\}', r'\1', line)
    line = re.sub(r'@strong\{([^}]*)\}', r'\1', line)
    line = re.sub(r'@\w+\{([^}]*)\}', r'\1', line)
    line = re.sub(r'@\w+', '', line)
    line = line.replace('{', '').replace('}', '')
    return line


# ============================================================================
# HTML → Markdown 转换器（复用 TCAD 的实现）
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
                          "copyright", "navigation"]
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
    except Exception as e:
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
        title = re.sub(r'<[^>]+>', '', title)
        title = re.sub(r'\s+', ' ', title)
        return title[:200]
    return "Untitled"


def process_texi_file(filepath: str) -> list[dict]:
    """解析 ngspice.texi，按章节拆分为多个文档"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"  [WARN] 读取失败 {filepath}: {e}", file=sys.stderr)
        return []

    # 按顶级章节拆分
    # 匹配 @chapter, @unnumbered, @appendix
    chapter_pattern = re.compile(
        r'^(@chapter|@unnumbered|@appendix|@majorheading)\s+(.+)$',
        re.MULTILINE
    )

    chapters = []
    last_end = 0
    last_title = "Introduction"

    for m in chapter_pattern.finditer(content):
        if last_end > 0:
            chapter_content = content[last_end:m.start()]
            chapters.append((last_title, chapter_content))
        last_title = _clean_texi(m.group(2))
        last_end = m.start()

    # 最后一个章节
    if last_end < len(content):
        chapters.append((last_title, content[last_end:]))

    # 如果没有找到章节，整体作为一个文档
    if not chapters:
        chapters = [("ngspice Manual", content)]

    docs = []
    for title, chapter_text in chapters:
        markdown = texi_to_markdown(chapter_text)
        if len(markdown) < 50:
            continue

        docs.append({
            "source": "manual",
            "file_path": filepath,
            "title": f"ngspice Manual - {title}",
            "content": markdown,
            "metadata": json.dumps({
                "type": "manual",
                "file": os.path.basename(filepath),
                "format": "texi",
                "chapter": title
            }, ensure_ascii=False)
        })

    return docs


def process_html_file(filepath: str, source_type: str) -> dict | None:
    """处理单个 HTML 文件"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"  [WARN] 读取失败 {filepath}: {e}", file=sys.stderr)
        return None

    title = extract_html_title(content)
    markdown = html_to_markdown(content)

    if len(markdown) < 50:
        return None

    return {
        "source": source_type,
        "file_path": filepath,
        "title": title,
        "content": markdown,
        "metadata": json.dumps({
            "type": source_type,
            "file": os.path.basename(filepath),
            "format": "html"
        }, ensure_ascii=False)
    }


def process_circuit_file(filepath: str, category: str) -> dict | None:
    """处理 .cir/.sp/.net 等电路文件，生成带描述的文档"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  [WARN] 读取失败 {filepath}: {e}", file=sys.stderr)
        return None

    if not lines:
        return None

    # 提取文件头注释（SPICE 注释以 * 开头）
    comment_lines = []
    for line in lines[:20]:
        stripped = line.strip()
        if stripped.startswith('*') or stripped.startswith('//'):
            comment_lines.append(stripped.lstrip('*/ ').strip())
        elif stripped and not stripped.startswith('.') and not stripped.startswith('$'):
            # 非注释、非指令行 = 电路描述开始
            if comment_lines:
                break
        elif stripped.startswith('$'):
            comment_lines.append(stripped[1:].strip())

    description = ' '.join(comment_lines) if comment_lines else ""

    # 从文件内容推断分析类型
    content_text = ''.join(lines)
    analysis_types = []
    if re.search(r'\.dc\b', content_text, re.IGNORECASE):
        analysis_types.append("DC analysis")
    if re.search(r'\.ac\b', content_text, re.IGNORECASE):
        analysis_types.append("AC analysis")
    if re.search(r'\.tran\b', content_text, re.IGNORECASE):
        analysis_types.append("Transient analysis")
    if re.search(r'\.op\b', content_text, re.IGNORECASE):
        analysis_types.append("Operating point")
    if re.search(r'\.noise\b', content_text, re.IGNORECASE):
        analysis_types.append("Noise analysis")
    if re.search(r'\.tf\b', content_text, re.IGNORECASE):
        analysis_types.append("Transfer function")
    if re.search(r'\.four\b', content_text, re.IGNORECASE):
        analysis_types.append("Fourier analysis")
    if re.search(r'\.pz\b', content_text, re.IGNORECASE):
        analysis_types.append("Pole-zero analysis")
    if re.search(r'\.disto\b', content_text, re.IGNORECASE):
        analysis_types.append("Distortion analysis")
    if re.search(r'\.sens\b', content_text, re.IGNORECASE):
        analysis_types.append("Sensitivity analysis")
    if re.search(r'\.mc\b', content_text, re.IGNORECASE):
        analysis_types.append("Monte Carlo")
    if re.search(r'\.control\b', content_text, re.IGNORECASE):
        analysis_types.append("Control script")

    # 推断器件类型
    device_types = []
    device_patterns = [
        (r'\bM\d+', "MOSFET"), (r'\bQ\d+', "BJT"), (r'\bD\d+', "Diode"),
        (r'\bJ\d+', "JFET"), (r'\bR\d+', "Resistor"), (r'\bC\d+', "Capacitor"),
        (r'\bL\d+', "Inductor"), (r'\bX\d+', "Subcircuit"),
        (r'\bS\d+', "Voltage switch"), (r'\bW\d+', "Current switch"),
        (r'\bB\d+', "Behavioral source"), (r'\bE\d+', "VCVS"),
        (r'\bF\d+', "CCCS"), (r'\bG\d+', "VCCS"), (r'\bH\d+', "CCVS"),
        (r'\bT\d+', "Transmission line"),
    ]
    for pattern, device_name in device_patterns:
        if re.search(pattern, content_text):
            device_types.append(device_name)

    # 检查 .model / .subckt
    has_model = bool(re.search(r'\.model\b', content_text, re.IGNORECASE))
    has_subckt = bool(re.search(r'\.subckt\b', content_text, re.IGNORECASE))

    # 构建内容
    content_parts = []
    if description:
        content_parts.append(f"# {description}")
    if analysis_types:
        content_parts.append(f"Analysis: {', '.join(analysis_types)}")
    if device_types:
        content_parts.append(f"Devices: {', '.join(list(dict.fromkeys(device_types))[:5])}")
    content_parts.append(f"Category: {category}")
    content_parts.append(f"File: {os.path.basename(filepath)}")
    if has_model:
        content_parts.append("Includes: .model definition")
    if has_subckt:
        content_parts.append("Includes: .subckt subcircuit")
    content_parts.append("")
    content_parts.append("```spice")
    content_parts.extend(line.rstrip() for line in lines)
    content_parts.append("```")

    content = '\n'.join(content_parts)

    # 标题
    basename = os.path.basename(filepath)
    title_parts = [category, basename]
    if description and len(description) < 80:
        title_parts.insert(1, description)
    title = " - ".join(title_parts)

    return {
        "source": "circuit",
        "file_path": filepath,
        "title": title,
        "content": content,
        "metadata": json.dumps({
            "type": "circuit",
            "category": category,
            "file": basename,
            "format": os.path.splitext(filepath)[1],
            "analysis": analysis_types,
            "devices": list(dict.fromkeys(device_types))[:5],
            "has_model": has_model,
            "has_subckt": has_subckt
        }, ensure_ascii=False)
    }


# ============================================================================
# 主处理流程
# ============================================================================

def main():
    print("=" * 60)
    print("ngspice 文档预处理")
    print("=" * 60)

    # 1. 处理 Texinfo 手册
    texi_file = RAW_DIR / "ngspice.texi"
    docs_output = str(OUTPUT_DIR / "documents.jsonl")
    total_docs = 0

    with open(docs_output, 'w', encoding='utf-8') as out:
        if texi_file.exists():
            print(f"\n[TEXI] 处理: {texi_file}")
            docs = process_texi_file(str(texi_file))
            for doc in docs:
                out.write(json.dumps(doc, ensure_ascii=False) + '\n')
                total_docs += 1
            print(f"  完成: {len(docs)} 个章节")
        else:
            print(f"[SKIP] texi 文件不存在: {texi_file}")

        # 1b. 处理 PDF 手册 (v46)
        pdf_file = RAW_DIR / "ngspice-46-manual.pdf"
        if pdf_file.exists() and pdf_file.stat().st_size > 1000:
            print(f"\n[PDF] 处理: {pdf_file}")
            try:
                import subprocess as sp
                result = sp.run(
                    ["pdftotext", "-layout", str(pdf_file), "-"],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode == 0 and result.stdout:
                    pdf_text = result.stdout
                    # 按顶级章节拆分: "数字  标题" 或 "Chapter 数字"
                    chapter_pat = re.compile(
                        r'\n(?=(?:\d{1,2}\s+[A-Z][A-Za-z\s]{10,}|Chapter \d+))',
                        re.MULTILINE
                    )
                    parts = chapter_pat.split(pdf_text)
                    if len(parts) < 5:
                        # 回退: 按二级标题 "数字.数字  标题"
                        chapter_pat2 = re.compile(
                            r'\n(?=\d{1,2}\.\d+\s+[A-Z])',
                            re.MULTILINE
                        )
                        parts = chapter_pat2.split(pdf_text)
                    if len(parts) < 5:
                        # 最终回退: 按 4000 字符分块
                        chunk_size = 4000
                        parts = [pdf_text[i:i+chunk_size] for i in range(0, len(pdf_text), chunk_size)]
                    pdf_count = 0
                    for idx, part in enumerate(parts):
                        part = part.strip()
                        if len(part) < 100:
                            continue
                        # 提取前 80 字符作为标题
                        first_line = part.split('\n')[0][:80]
                        doc = {
                            "source": "manual",
                            "file_path": str(pdf_file),
                            "title": f"ngspice-46 Manual - Part {idx+1}: {first_line}",
                            "content": part,
                            "metadata": json.dumps({
                                "type": "manual",
                                "file": "ngspice-46-manual.pdf",
                                "format": "pdf",
                                "part": idx + 1,
                                "total_parts": len(parts)
                            }, ensure_ascii=False)
                        }
                        out.write(json.dumps(doc, ensure_ascii=False) + '\n')
                        pdf_count += 1
                        total_docs += 1
                    print(f"  完成: {pdf_count} 个分块")
                else:
                    print(f"  [WARN] pdftotext 失败: {result.stderr[:200]}")
            except FileNotFoundError:
                print("  [WARN] pdftotext 未安装，跳过 PDF")
            except Exception as e:
                print(f"  [WARN] PDF 处理失败: {e}")

        # 1c. 处理 README 文档 (v46)
        readme_files = [
            ("ngspice-46-osdi-howto.txt", "reference"),
            ("ngspice-46-osdi.md", "reference"),
            ("ngspice-46-optran-readme.txt", "reference"),
            ("ngspice-46-vdmos-readme.txt", "reference"),
            ("ngspice-46-cpl-gc-readme.txt", "reference"),
            ("ngspice-46-see-generator.txt", "reference"),
        ]
        for fname, stype in readme_files:
            fpath = RAW_DIR / fname
            if not fpath.exists() or fpath.stat().st_size < 50:
                continue
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().strip()
                if len(content) < 50:
                    continue
                doc = {
                    "source": stype,
                    "file_path": str(fpath),
                    "title": f"ngspice-46 {fname}",
                    "content": content,
                    "metadata": json.dumps({
                        "type": stype,
                        "file": fname,
                        "format": "text"
                    }, ensure_ascii=False)
                }
                out.write(json.dumps(doc, ensure_ascii=False) + '\n')
                total_docs += 1
                print(f"  [README] {fname}")
            except Exception as e:
                print(f"  [WARN] {fname}: {e}")

        # 2. 处理 HTML 文档 (v46)
        html_files = [
            ("ngspice-46-tutorial.html", "tutorial"),
            ("ngspice-46-control-language-tutorial.html", "tutorial"),
            ("ngspice-46-electrothermal-tutorial.html", "tutorial"),
            ("ngspice-46-modelparams.html", "reference"),
            ("ngspice-46-spdevs.html", "reference"),
            ("ngspice-46-tclexamples.html", "tutorial"),
            ("ngspice-46-tclspice.html", "tutorial"),
            ("ngspice-46-tclusers.html", "tutorial"),
            ("ngspice-46-applic.html", "application"),
            ("ngspice-46-devdocs.html", "developer"),
            ("ngspice-46-recipes.html", "tutorial"),
            ("ngspice-46-power-applications.html", "application"),
            ("ngspice-46-tutorials-overview.html", "tutorial"),
            ("ngspice-46-docs.html", "reference"),
            ("ngspice-46-faq.html", "reference"),
        ]

        html_count = 0
        for fname, source_type in html_files:
            fpath = RAW_DIR / fname
            if not fpath.exists():
                continue
            # 跳过空文件
            if fpath.stat().st_size < 100:
                print(f"  [SKIP] 文件过小: {fname}")
                continue

            doc = process_html_file(str(fpath), source_type)
            if doc and doc["content"]:
                out.write(json.dumps(doc, ensure_ascii=False) + '\n')
                html_count += 1
                total_docs += 1
                print(f"  [HTML] {fname} -> {len(doc['content'])} chars")

        print(f"\n[HTML] 完成: {html_count} 个文档")

        # 3. 处理电路示例
        circuit_count = 0
        if os.path.exists(EXAMPLES_DIR):
            print(f"\n[CIRCUIT] 处理示例目录: {EXAMPLES_DIR}")
            for category_dir in sorted(os.listdir(EXAMPLES_DIR)):
                cat_path = os.path.join(EXAMPLES_DIR, category_dir)
                if not os.path.isdir(cat_path):
                    continue

                for fname in sorted(os.listdir(cat_path)):
                    fpath = os.path.join(cat_path, fname)
                    if not os.path.isfile(fpath):
                        continue

                    # 支持的文件类型
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in ('.cir', '.sp', '.net', '.mod', '.lib',
                                   '.cmd', '.tcl', '.pro', '.script'):
                        continue

                    doc = process_circuit_file(fpath, category_dir)
                    if doc and doc["content"]:
                        out.write(json.dumps(doc, ensure_ascii=False) + '\n')
                        circuit_count += 1
                        total_docs += 1

                if circuit_count > 0 and circuit_count % 50 == 0:
                    print(f"  已处理 {circuit_count} 个电路文件...")

        print(f"\n[CIRCUIT] 完成: {circuit_count} 个文档")

    print(f"\n{'='*60}")
    print(f"总计: {total_docs} 个文档")
    print(f"输出: {docs_output}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
