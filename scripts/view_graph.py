#!/usr/bin/env python3
# ruff: noqa: E501
"""Graph viewer — renders Mermaid diagrams as HTML and opens in browser.

Usage:
    python scripts/view_graph.py                    # 打开当前 LangGraph 主图
    python scripts/view_graph.py --main             # 仅主图
    python scripts/view_graph.py --sub g4_codegen   # 仅 G4 代码生成子图
    python scripts/view_graph.py --all              # 当前主图 + 所有子图
    python scripts/view_graph.py --source static    # 使用手工整理版 Mermaid 总览
    python scripts/view_graph.py --no-open          # 仅生成，不打开浏览器
"""

from __future__ import annotations

import argparse
import html
import tempfile
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_core.visualization import (
    draw_all as draw_static_all,
)
from agent_core.visualization import (
    draw_combined as draw_static_combined,
)
from agent_core.visualization import (
    draw_main_graph as draw_static_main_graph,
)
from agent_core.visualization import (
    draw_subgraph as draw_static_subgraph,
)


def _build_html_page(title: str, mermaid_content: str) -> str:
    """Wrap a single Mermaid diagram in a full HTML page."""
    escaped = html.escape(mermaid_content)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    max-width: 1200px;
    margin: 0 auto;
    padding: 24px;
    background: #fafafa;
    color: #333;
  }}
  h1 {{
    color: #1976D2;
    border-bottom: 2px solid #E3F2FD;
    padding-bottom: 8px;
  }}
  .mermaid {{
    background: white;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 24px;
    margin: 16px 0;
    overflow-x: auto;
  }}
  .legend {{
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin: 16px 0;
    padding: 12px;
    background: white;
    border-radius: 8px;
    border: 1px solid #e0e0e0;
  }}
  .legend-item {{
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
  }}
  .legend-swatch {{
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 2px solid;
  }}
  .arrow-legend {{
    margin: 12px 0;
    padding: 12px;
    background: white;
    border-radius: 8px;
    border: 1px solid #e0e0e0;
    font-size: 13px;
    line-height: 1.8;
  }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>

<div class="legend">
  <div class="legend-item"><div class="legend-swatch" style="background:#E8F5E9;border-color:#388E3C"></div>工作区</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#FFF3E0;border-color:#F57C00"></div>I/O</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#E3F2FD;border-color:#1976D2"></div>核心节点</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#FCE4EC;border-color:#C62828"></div>守卫/门禁</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#F3E5F5;border-color:#7B1FA2"></div>代码生成</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#FFF9C4;border-color:#F9A825"></div>门禁检查</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#E0F7FA;border-color:#00838F"></div>产物/报告</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#F5F5F5;border-color:#757575"></div>子图包装</div>
</div>

<div class="arrow-legend">
  <b>箭头类型：</b>
  <code>───▶</code> 正常流转 &nbsp;|&nbsp;
  <code>═══▶</code> 阻断/失败 &nbsp;|&nbsp;
  <code>╌╌╌▶</code> 重试回路
</div>

<div class="mermaid">
{escaped}
</div>

<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  mermaid.initialize({{
    startOnLoad: true,
    theme: 'default',
    flowchart: {{ useMaxWidth: true, htmlLabels: true, curve: 'basis' }},
    securityLevel: 'loose',
  }});
</script>
</body>
</html>"""


def _compile_if_needed(graph_or_compiled: Any) -> Any:
    if hasattr(graph_or_compiled, "get_graph"):
        return graph_or_compiled
    return graph_or_compiled.compile()


def _langgraph_builders() -> dict[str, tuple[str, Callable[[], Any]]]:
    """Return actual LangGraph builders keyed by user-facing subgraph name."""
    from agent_core.artifacts import build_artifact_subgraph
    from agent_core.context import build_context_subgraph
    from agent_core.gates import build_gate_validation_subgraph
    from agent_core.graph.main_graph import build_main_graph
    from agent_core.graph.subgraphs.g4_codegen_graph import build_g4_codegen_subgraph
    from agent_core.graph.subgraphs.g4_modeling_graph import build_g4_modeling_subgraph
    from agent_core.graph.subgraphs.human_confirmation_graph import (
        build_human_confirmation_subgraph,
    )
    from agent_core.patching import build_patch_subgraph
    from agent_core.planning import build_task_planning_subgraph
    from agent_core.reports import build_report_subgraph

    return {
        "main_graph": ("RadAgent Main Graph", build_main_graph),
        "context": ("Context Subgraph", build_context_subgraph),
        "task_planning": ("Task Planning Subgraph", build_task_planning_subgraph),
        "g4_modeling": ("G4 Modeling Subgraph", build_g4_modeling_subgraph),
        "human_confirmation": (
            "Human Confirmation Subgraph",
            build_human_confirmation_subgraph,
        ),
        "g4_codegen": ("G4 Codegen Subgraph", build_g4_codegen_subgraph),
        "patch": ("Patch Subgraph", build_patch_subgraph),
        "gate_validation": ("Gate Validation Subgraph", build_gate_validation_subgraph),
        "artifact": ("Artifact Subgraph", build_artifact_subgraph),
        "report": ("Report Subgraph", build_report_subgraph),
    }


def _draw_langgraph(name: str) -> str:
    builders = _langgraph_builders()
    if name not in builders:
        available = ", ".join(sorted(builders))
        raise ValueError(f"Unknown graph '{name}'. Available: {available}")
    _, builder = builders[name]
    compiled = _compile_if_needed(builder())
    return compiled.get_graph().draw_mermaid()


def _draw_langgraph_all() -> dict[str, str]:
    return {name: _draw_langgraph(name) for name in _langgraph_builders()}


def _static_diagrams_for_all() -> dict[str, str]:
    diagrams = draw_static_all()
    if "human_confirmation" not in diagrams:
        diagrams["human_confirmation"] = (
            "flowchart TB\n"
            "    human_confirmation_subgraph[Human Confirmation 子图]\n"
            "    human_confirmation_subgraph --> END((END))\n"
        )
    return diagrams


def _build_multi_page(title: str, diagrams: dict[str, str]) -> str:
    """Build an HTML page with multiple diagrams, each in its own tab."""
    tabs_html: list[str] = []
    panels_html: list[str] = []

    for i, (name, content) in enumerate(diagrams.items()):
        active = "active" if i == 0 else ""
        display = name.replace("_", " ").title()
        tabs_html.append(
            f'<button class="tab-btn {active}" onclick="switchTab(event, \'tab-{name}\')">'
            f"{html.escape(display)}</button>"
        )
        escaped = html.escape(content)
        panels_html.append(
            f'<div id="tab-{name}" class="tab-panel {active}">'
            f'<pre class="mermaid">{escaped}</pre>'
            f"</div>"
        )

    tabs = "\n".join(tabs_html)
    panels = "\n".join(panels_html)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    max-width: 1200px;
    margin: 0 auto;
    padding: 24px;
    background: #fafafa;
    color: #333;
  }}
  h1 {{ color: #1976D2; }}
  .tabs {{ display: flex; flex-wrap: wrap; gap: 4px; margin: 16px 0; }}
  .tab-btn {{
    padding: 8px 16px;
    border: 1px solid #ccc;
    border-radius: 6px 6px 0 0;
    background: #f5f5f5;
    cursor: pointer;
    font-size: 14px;
  }}
  .tab-btn:hover {{ background: #e3f2fd; }}
  .tab-btn.active {{
    background: #1976D2;
    color: white;
    border-color: #1976D2;
  }}
  .tab-panel {{ display: none; background: white; border: 1px solid #e0e0e0;
                border-radius: 0 8px 8px 8px; padding: 24px; }}
  .tab-panel.active {{ display: block; }}
  .mermaid {{ overflow-x: auto; }}
  .legend {{
    display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0;
    padding: 12px; background: white; border-radius: 8px; border: 1px solid #e0e0e0;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 13px; }}
  .legend-swatch {{ width: 16px; height: 16px; border-radius: 3px; border: 2px solid; }}
  .arrow-legend {{
    margin: 12px 0; padding: 12px; background: white; border-radius: 8px;
    border: 1px solid #e0e0e0; font-size: 13px; line-height: 1.8;
  }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>

<div class="legend">
  <div class="legend-item"><div class="legend-swatch" style="background:#E8F5E9;border-color:#388E3C"></div>工作区</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#FFF3E0;border-color:#F57C00"></div>I/O</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#E3F2FD;border-color:#1976D2"></div>核心节点</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#FCE4EC;border-color:#C62828"></div>守卫/门禁</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#F3E5F5;border-color:#7B1FA2"></div>代码生成</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#FFF9C4;border-color:#F9A825"></div>门禁检查</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#E0F7FA;border-color:#00838F"></div>产物/报告</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#F5F5F5;border-color:#757575"></div>子图包装</div>
</div>

<div class="arrow-legend">
  <b>箭头类型：</b>
  <code>───▶</code> 正常流转 &nbsp;|&nbsp;
  <code>═══▶</code> 阻断/失败 &nbsp;|&nbsp;
  <code>╌╌╌▶</code> 重试回路
</div>

<div class="tabs">
{tabs}
</div>
{panels}

<script>
function switchTab(evt, tabId) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(tabId).classList.add('active');
  evt.currentTarget.classList.add('active');
  // Re-render mermaid in newly visible tab
  if (window.mermaid) {{
    window.mermaid.run({{nodes: document.querySelectorAll('#' + tabId + ' .mermaid')}});
  }}
}}
</script>

<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  window.mermaid = mermaid;
  mermaid.initialize({{
    startOnLoad: true,
    theme: 'default',
    flowchart: {{ useMaxWidth: true, htmlLabels: true, curve: 'basis' }},
    securityLevel: 'loose',
  }});
</script>
</body>
</html>"""


def view_graph(
    main: bool = False,
    sub: str | None = None,
    all_graphs: bool = False,
    no_open: bool = False,
    output: str | None = None,
    source: str = "langgraph",
) -> Path:
    """Generate and optionally open graph visualization HTML.

    Returns path to the generated HTML file.
    """
    use_langgraph = source == "langgraph"
    source_label = "当前 LangGraph" if use_langgraph else "静态 Mermaid"
    if sub:
        title = f"RadAgent — {sub} 子图 ({source_label})"
        mermaid = _draw_langgraph(sub) if use_langgraph else draw_static_subgraph(sub)
        html_content = _build_html_page(title, mermaid)
    elif main:
        title = f"RadAgent — 主图 ({source_label})"
        mermaid = _draw_langgraph("main_graph") if use_langgraph else draw_static_main_graph()
        html_content = _build_html_page(title, mermaid)
    elif all_graphs:
        title = f"RadAgent — 全部图结构 ({source_label})"
        diagrams = _draw_langgraph_all() if use_langgraph else _static_diagrams_for_all()
        html_content = _build_multi_page(title, diagrams)
    else:
        title = f"RadAgent — 图结构总览 ({source_label})"
        mermaid = _draw_langgraph("main_graph") if use_langgraph else draw_static_combined()
        html_content = _build_html_page(title, mermaid)

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_content, encoding="utf-8")
    else:
        tmp = tempfile.NamedTemporaryFile(
            suffix=".html",
            prefix="radagent_graph_",
            delete=False,
            mode="w",
            encoding="utf-8",
        )
        tmp.write(html_content)
        tmp.close()
        out_path = Path(tmp.name)

    if not no_open:
        webbrowser.open(f"file://{out_path}")
        print(f"  📊 已在浏览器中打开: {out_path}")
    else:
        print(f"  📄 已生成: {out_path}")

    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="RadAgent Graph Viewer — 在浏览器中查看图结构")
    parser.add_argument("--main", action="store_true", help="仅查看主图")
    parser.add_argument("--sub", type=str, default=None, help="查看指定子图")
    parser.add_argument("--all", action="store_true", dest="all_graphs", help="查看所有图")
    parser.add_argument(
        "--source",
        choices=["langgraph", "static"],
        default="langgraph",
        help="图数据来源：langgraph=当前代码编译图，static=手工整理 Mermaid",
    )
    parser.add_argument("--no-open", action="store_true", help="仅生成 HTML，不打开浏览器")
    parser.add_argument("-o", "--output", type=str, default=None, help="指定输出 HTML 路径")

    args = parser.parse_args()
    view_graph(
        main=args.main,
        sub=args.sub,
        all_graphs=args.all_graphs,
        no_open=args.no_open,
        output=args.output,
        source=args.source,
    )


if __name__ == "__main__":
    main()
