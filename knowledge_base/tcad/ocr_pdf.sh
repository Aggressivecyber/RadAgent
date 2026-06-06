#!/bin/bash
# OCR 扫描 PDF → Markdown，用于嵌入 RAG
# 用法: bash ocr_pdf.sh <input.pdf> <output_dir>

set -e
PDF="$1"
OUTDIR="$2"
TMPDIR=$(mktemp -d)

echo "[OCR] $PDF → $OUTDIR"
echo "[OCR] 临时目录: $TMPDIR"

# 1. PDF → 图片 (300 DPI)
echo "[OCR] 转换 PDF 为图片..."
pdftoppm -png -r 300 "$PDF" "$TMPDIR/page"
PAGE_COUNT=$(ls "$TMPDIR"/page-*.png 2>/dev/null | wc -l)
echo "[OCR] 共 $PAGE_COUNT 页"

# 2. 逐页 OCR
OUTPUT="$OUTDIR/output.md"
> "$OUTPUT"

for img in "$TMPDIR"/page-*.png; do
    page_num=$(basename "$img" | sed 's/page-//;s/.png//')
    text=$(tesseract "$img" stdout -l eng+chi_sim 2>/dev/null)
    if [ -n "$text" ]; then
        echo "--- Page $page_num ---" >> "$OUTPUT"
        echo "$text" >> "$OUTPUT"
        echo "" >> "$OUTPUT"
    fi
    # 进度
    if (( page_num % 10 == 0 )); then
        echo "[OCR] 已处理 $page_num / $PAGE_COUNT 页..."
    fi
done

echo "[OCR] 完成! $PAGE_COUNT 页 → $(wc -l < "$OUTPUT") 行"
echo "[OCR] 文件: $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"

# 清理
rm -rf "$TMPDIR"
