#!/usr/bin/env python3
"""
TCAD 课程材料预处理脚本
将课程实验代码（.cmd/.par/.sde/.tcl 等）转为 JSONL 格式
用于添加到 TCAD RAG 知识库
"""

import json
import os
import sys
from pathlib import Path

COURSE_ROOT = "/home/rylan/workspace/code_files/代码文件"
OUTPUT_FILE = Path(__file__).parent / "data" / "course_materials.jsonl"

# 需要处理的代码文件扩展名
CODE_EXTS = {'.cmd', '.tcl', '.sde', '.par', '.prf', '.c', '.gds', '.tdb'}


def process_course_file(filepath: str) -> dict | None:
    """处理课程代码文件，生成带上下文描述的文档"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  [WARN] 读取失败 {filepath}: {e}", file=sys.stderr)
        return None

    if not lines:
        return None

    # 提取注释作为描述
    comment_lines = []
    for line in lines[:30]:
        stripped = line.strip()
        if stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('$'):
            comment_lines.append(stripped.lstrip('#/$/ ').strip())
        elif stripped and not stripped.startswith(('#', '//', '$')):
            break

    description = ' '.join(comment_lines) if comment_lines else ""

    # 从路径推断上下文
    rel_path = os.path.relpath(filepath, COURSE_ROOT)
    parts = rel_path.split(os.sep)
    
    # 章节信息
    chapter = parts[0] if len(parts) > 0 else ""
    # 项目/日期名
    project_name = parts[-2] if len(parts) >= 2 else ""
    
    # 推断工具类型
    basename = os.path.basename(filepath)
    name_no_ext = os.path.splitext(basename)[0]
    ext = os.path.splitext(basename)[1].lower()
    
    tool_hints = []
    if 'fps' in name_no_ext.lower() or 'process' in name_no_ext.lower():
        tool_hints.append("Sentaurus Process")
    if 'sdevice' in name_no_ext.lower() or '_des' in name_no_ext.lower() or ext == '.prf':
        tool_hints.append("Sentaurus Device")
    if 'svisual' in name_no_ext.lower() or '_vis' in name_no_ext.lower():
        tool_hints.append("Sentaurus Visual")
    if 'sde' in name_no_ext.lower() or ext == '.sde':
        tool_hints.append("Sentaurus Structure Editor")
    if 'swb' in name_no_ext.lower():
        tool_hints.append("Sentaurus Workbench")
    if ext == '.c':
        tool_hints.append("Sentaurus LDE / Macro Command")
    if ext in ('.gds', '.tdb'):
        tool_hints.append("Layout / GDSII")

    # 从目录名推断器件类型
    device_type = ""
    path_lower = rel_path.lower()
    if 'mosfet' in path_lower or 'mos' in path_lower:
        device_type = "MOSFET"
    elif 'igbt' in path_lower:
        device_type = "IGBT"
    elif 'pn' in path_lower or 'diode' in path_lower:
        device_type = "PN Diode"
    elif 'bjt' in path_lower:
        device_type = "BJT"
    elif 'finfet' in path_lower:
        device_type = "FinFET"
    elif 'ldmos' in path_lower:
        device_type = "LDMOS"
    elif 'gan' in path_lower or 'hfet' in path_lower:
        device_type = "GaN HFET"
    elif 'sic' in path_lower:
        device_type = "SiC MOSFET"
    elif 'tunneling' in path_lower or 'tfet' in path_lower:
        device_type = "Tunneling FET / TFET"
    elif 'ga2o3' in path_lower:
        device_type = "Ga2O3 Device"
    elif 'sige' in path_lower:
        device_type = "SiGe Diode"
    elif 'photo' in path_lower:
        device_type = "Photo Diode"
    elif 'heavyion' in path_lower or 'trap' in path_lower or 'radiation' in path_lower:
        device_type = "Radiation Effects / Heavy Ion"
    elif 'schottky' in path_lower:
        device_type = "Schottky Diode"
    elif 'spice' in path_lower:
        device_type = "SPICE Model Extraction"
    elif 'electrode' in path_lower:
        device_type = "Electrode Models"
    elif 'mobility' in path_lower:
        device_type = "Mobility Models"
    elif 'temperature' in path_lower or 'workfunction' in path_lower:
        device_type = "Temperature / Workfunction"
    elif 'ac' in path_lower or 'circuit' in path_lower:
        device_type = "AC / Circuit Simulation"
    elif 'calibrate' in path_lower or 'parameter' in path_lower:
        device_type = "Device Calibration"
    elif 'mesh' in path_lower or 'adaptive' in path_lower or 'static_mesh' in path_lower:
        device_type = "Mesh Generation"
    elif 'polarization' in path_lower:
        device_type = "Polarization (GaN)"
    elif 'doping' in path_lower or 'donor' in path_lower or 'acceptor' in path_lower:
        device_type = "Doping Profile"
    elif 'band' in path_lower:
        device_type = "Band Structure"

    # 构建内容
    content_parts = []
    content_parts.append(f"# TCAD 课程实验: {project_name}")
    content_parts.append(f"章节: {chapter}")
    if device_type:
        content_parts.append(f"器件类型: {device_type}")
    if tool_hints:
        content_parts.append(f"工具: {', '.join(tool_hints)}")
    if description:
        content_parts.append(f"描述: {description}")
    content_parts.append(f"文件: {rel_path}")
    content_parts.append("")
    content_parts.append("```")
    content_parts.extend(line.rstrip() for line in lines)
    content_parts.append("```")

    content = '\n'.join(content_parts)

    # 标题
    title_parts = ["课程实验"]
    if chapter:
        title_parts.append(chapter)
    if project_name:
        title_parts.append(project_name)
    if device_type:
        title_parts.append(device_type)
    title_parts.append(basename)
    title = " - ".join(title_parts)

    return {
        "source": "course",
        "file_path": filepath,
        "title": title,
        "content": content,
        "metadata": json.dumps({
            "type": "course_code",
            "chapter": chapter,
            "project": project_name,
            "device_type": device_type,
            "file": rel_path,
            "format": ext,
            "tools": tool_hints,
            "description": description
        })
    }


def main():
    if not os.path.exists(COURSE_ROOT):
        print(f"[ERROR] 目录不存在: {COURSE_ROOT}", file=sys.stderr)
        sys.exit(1)

    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    
    count = 0
    skipped = 0
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as out:
        for root, dirs, files in os.walk(COURSE_ROOT):
            # 跳过压缩文件和备份文件
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('__pycache__',)]
            
            for fname in sorted(files):
                ext = os.path.splitext(fname)[1].lower()
                if ext not in CODE_EXTS:
                    continue
                
                # 跳过备份文件
                if fname.endswith('~') or fname.endswith('.backup'):
                    skipped += 1
                    continue
                
                filepath = os.path.join(root, fname)
                
                # 跳过太大的文件 (>50KB)
                fsize = os.path.getsize(filepath)
                rel_path = os.path.relpath(filepath, COURSE_ROOT)
                if fsize > 50000:
                    print(f"  [SKIP] 文件过大 ({fsize//1024}KB): {rel_path}", file=sys.stderr)
                    skipped += 1
                    continue
                
                doc = process_course_file(filepath)
                if doc and doc["content"]:
                    out.write(json.dumps(doc, ensure_ascii=False) + '\n')
                    count += 1
                    
                    if count % 100 == 0:
                        print(f"  已处理 {count} 个文件...", file=sys.stderr)
    
    print(f"\n[完成] 处理了 {count} 个文件, 跳过 {skipped} 个", file=sys.stderr)
    print(f"输出: {OUTPUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
