from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "device_canvas" / "index.html"
CORE = ROOT / "device_canvas" / "cad_core.js"


def main():
    html = INDEX.read_text(encoding="utf-8")
    core = CORE.read_text(encoding="utf-8")

    required_theme_tokens = [
        '--radagent-font:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI","Noto Sans CJK SC",Roboto,sans-serif;',
        '--radagent-code-font:"JetBrains Mono","SFMono-Regular",Consolas,ui-monospace,monospace;',
        "--paper:#fbfaf7;",
        "--panel:#ffffff;",
        "--ink:#171614;",
        "--muted:#68625a;",
        "--line:#ded9cf;",
        "--accent:#b94138;",
        "--accent-dark:#8f2924;",
    ]
    for token in required_theme_tokens:
        assert token in html, token

    assert 'style id="radagent-cad-theme"' in html
    assert 'id="tech-theme"' not in html
    assert "#0066ff" not in html
    assert "#00e5ff" not in html
    assert "cyan" not in html.lower()
    assert "electric blue" not in html.lower()

    assert 'const OUTLINE="#b94138";' in core
    assert 'const ACCENT="#8f2924";' in core
    print({"theme": "radagent", "tokens": len(required_theme_tokens)})


if __name__ == "__main__":
    main()
