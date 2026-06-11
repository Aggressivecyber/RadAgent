from __future__ import annotations

import pytest
from agent_core.tui.i18n import RADAGENT_BRAND_MARK, TUILanguage, label, parse_language


def test_parse_language_accepts_english_and_chinese_names() -> None:
    assert parse_language("en") is TUILanguage.ENGLISH
    assert parse_language("english") is TUILanguage.ENGLISH
    assert parse_language("zh") is TUILanguage.CHINESE
    assert parse_language("中文") is TUILanguage.CHINESE


def test_parse_language_rejects_bilingual_mode() -> None:
    with pytest.raises(ValueError, match="Language must be"):
        parse_language("bilingual")


def test_labels_return_one_language_at_a_time() -> None:
    assert label("options.title", TUILanguage.ENGLISH) == "Options"
    assert label("options.title", TUILanguage.CHINESE) == "选项"
    assert "/" not in label("options.title", TUILanguage.ENGLISH)
    assert "/" not in label("options.title", TUILanguage.CHINESE)


def test_footer_labels_are_not_bilingual() -> None:
    english = label("footer", TUILanguage.ENGLISH)
    chinese = label("footer", TUILanguage.CHINESE)

    assert "Ctrl+P options" in english
    assert "Ctrl+O artifacts" in english
    assert "产物" not in english
    assert "Ctrl+P 选项" in chinese
    assert "Ctrl+O 产物" in chinese
    assert "artifacts" not in chinese


def test_brand_mark_is_complete_line_art_without_font_copy() -> None:
    ready = label("brand.ready", TUILanguage.ENGLISH)
    lines = RADAGENT_BRAND_MARK.splitlines()

    assert any(char in RADAGENT_BRAND_MARK for char in "-_/\\")
    assert "█" not in RADAGENT_BRAND_MARK
    assert len(lines) >= 5
    assert all(len(line.rstrip()) >= 40 for line in lines)
    assert "____" in lines[0]
    assert r"\____" in RADAGENT_BRAND_MARK
    assert "JetBrains Mono" not in ready
    assert "font" not in ready.lower()
