from __future__ import annotations

from enum import StrEnum


class TUILanguage(StrEnum):
    """Supported single-language modes for the terminal UI."""

    ENGLISH = "en"
    CHINESE = "zh"


DEFAULT_LANGUAGE = TUILanguage.ENGLISH
RADAGENT_BRAND_MARK = "\n".join(
    [
        r"    ____                 __        ___                       __ ",
        r"   / __ \  ____ _  ___ _/ /       /   | ____ _ ___   ____   / /_",
        r"  / /_/ / / __ `/ / ___/ /       / /| |/ __ `// _ \ / __ \ / __/",
        r" / ___ / / /_/ /_/ /__/ /_      / ___ / /_/ // ___// / / // /_  ",
        r"/_/  |_| \__,___/\_______/     /_/  |_\__, / \___//_/ /_/ \__/  ",
        r"                                      /___/                     ",
    ]
)

_LANGUAGE_ALIASES = {
    "en": TUILanguage.ENGLISH,
    "eng": TUILanguage.ENGLISH,
    "english": TUILanguage.ENGLISH,
    "zh": TUILanguage.CHINESE,
    "cn": TUILanguage.CHINESE,
    "中文": TUILanguage.CHINESE,
    "汉语": TUILanguage.CHINESE,
    "chinese": TUILanguage.CHINESE,
}

_LABELS: dict[str, dict[TUILanguage, str]] = {
    "prompt.placeholder": {
        TUILanguage.ENGLISH: "Ask RadAgent, or run: /run <simulation request>",
        TUILanguage.CHINESE: "询问 RadAgent，或运行：/run <仿真请求>",
    },
    "footer": {
        TUILanguage.ENGLISH: (
            "Ctrl+L input  Ctrl+P options  Ctrl+I inspect  Ctrl+T trace  Ctrl+O artifacts  "
            "F1 help  Ctrl+C stop"
        ),
        TUILanguage.CHINESE: (
            "Ctrl+L 输入  Ctrl+P 选项  Ctrl+I 检查  Ctrl+T trace  Ctrl+O 产物  "
            "F1 帮助  Ctrl+C 停止"
        ),
    },
    "brand.ready": {
        TUILanguage.ENGLISH: RADAGENT_BRAND_MARK,
        TUILanguage.CHINESE: RADAGENT_BRAND_MARK,
    },
    "options.title": {
        TUILanguage.ENGLISH: "Options",
        TUILanguage.CHINESE: "选项",
    },
    "options.language": {
        TUILanguage.ENGLISH: "Language",
        TUILanguage.CHINESE: "语言",
    },
    "options.current": {
        TUILanguage.ENGLISH: "Current",
        TUILanguage.CHINESE: "当前",
    },
    "options.theme": {
        TUILanguage.ENGLISH: "Theme",
        TUILanguage.CHINESE: "主题",
    },
    "options.controls": {
        TUILanguage.ENGLISH: "Up/Down select  Left/Right change  Enter apply",
        TUILanguage.CHINESE: "上下选择  左右切换  Enter 应用",
    },
    "options.switch": {
        TUILanguage.ENGLISH: "Switch: /options en | /options zh",
        TUILanguage.CHINESE: "切换：/options en | /options zh",
    },
    "options.context_window": {
        TUILanguage.ENGLISH: "Context window: 100k, 200k, 500k, 1m; custom values use k",
        TUILanguage.CHINESE: "上下文窗口：100k, 200k, 500k, 1m；自定义数值单位为 k",
    },
    "options.ctrl_o": {
        TUILanguage.ENGLISH: "Ctrl+O artifacts: open outputs for the active job.",
        TUILanguage.CHINESE: "Ctrl+O 产物：打开当前任务的输出文件。",
    },
    "options.logs": {
        TUILanguage.ENGLISH: "Logs: /logs opens internal routing and service events.",
        TUILanguage.CHINESE: "日志：/logs 打开内部路由和服务事件。",
    },
    "options.jobs": {
        TUILanguage.ENGLISH: "Jobs: /jobs lists previous and active jobs.",
        TUILanguage.CHINESE: "任务：/jobs 查看历史和当前任务。",
    },
    "options.updated": {
        TUILanguage.ENGLISH: "Options updated",
        TUILanguage.CHINESE: "选项已更新",
    },
    "commands.title": {
        TUILanguage.ENGLISH: "Commands",
        TUILanguage.CHINESE: "命令",
    },
    "artifacts.title": {
        TUILanguage.ENGLISH: "Artifacts",
        TUILanguage.CHINESE: "产物",
    },
    "artifacts.empty": {
        TUILanguage.ENGLISH: "No artifacts for the active job.",
        TUILanguage.CHINESE: "当前任务没有产物。",
    },
    "jobs.title": {
        TUILanguage.ENGLISH: "Jobs",
        TUILanguage.CHINESE: "任务",
    },
    "jobs.empty": {
        TUILanguage.ENGLISH: "No jobs found.",
        TUILanguage.CHINESE: "没有找到任务。",
    },
    "status.title": {
        TUILanguage.ENGLISH: "Status",
        TUILanguage.CHINESE: "状态",
    },
    "ready.title": {
        TUILanguage.ENGLISH: "RadAgent",
        TUILanguage.CHINESE: "RadAgent",
    },
    "thinking.analyzing": {
        TUILanguage.ENGLISH: "Analyzing simulation request...",
        TUILanguage.CHINESE: "分析仿真需求...",
    },
    "thinking.done": {
        TUILanguage.ENGLISH: "Copilot response ready.",
        TUILanguage.CHINESE: "Copilot 回复已就绪。",
    },
}


def parse_language(value: str) -> TUILanguage:
    """Parse user-facing language names into a TUI language mode."""
    normalized = value.strip().lower()
    if normalized in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[normalized]
    raise ValueError("Language must be one of: en, english, zh, 中文")


def language_name(language: TUILanguage) -> str:
    """Return the localized display name for a language option."""
    return {
        TUILanguage.ENGLISH: "English",
        TUILanguage.CHINESE: "中文",
    }[language]


def label(key: str, language: TUILanguage) -> str:
    """Return a localized label for the active TUI language."""
    try:
        return _LABELS[key][language]
    except KeyError:
        return key
