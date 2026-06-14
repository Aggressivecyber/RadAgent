"""OpenAI function-calling schemas for codegen dev tools.

These dicts are sent verbatim as the ``tools`` field to the model gateway.
Keep descriptions tight and prescriptive — they are the model's only contract
for how to drive the build-fix loop.
"""

from __future__ import annotations

from typing import Any

READ_FILE: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": (
            "Read a file under the project directory. Returns the content with "
            "line numbers. Use this to inspect generated source before editing."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from the project root, e.g. 'src/Hit.cc'.",
                },
                "offset": {
                    "type": "integer",
                    "description": "1-based starting line (optional).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max lines to return (optional, default 200).",
                },
            },
            "required": ["path"],
        },
    },
}

EDIT_FILE: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "edit_file",
        "description": (
            "Replace exactly one occurrence of old_string with new_string in a "
            "project file. old_string MUST be unique in the file; if it matches "
            "zero or multiple places the edit is rejected. Include enough "
            "context lines in old_string to make it unique."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_string": {"type": "string", "description": "Exact existing text to replace (must be unique)."},
                "new_string": {"type": "string", "description": "Replacement text."},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
}

WRITE_FILE: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "Overwrite a project file with full new content. Use for new files or full rewrites.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string", "description": "Complete new file content."},
            },
            "required": ["path", "content"],
        },
    },
}

LIST_FILES: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "list_files",
        "description": (
            "List project-relative source/config files matching a glob. Ignores "
            "build artifacts. Use this to find headers or sources before reading."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "glob": {
                    "type": "string",
                    "description": "Relative glob such as 'include/*.hh' or 'src/*Detector*'.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum file paths to return (optional, default 50).",
                },
            },
            "required": [],
        },
    },
}

SEARCH_TEXT: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_text",
        "description": (
            "Search project source/config files for a literal string. Returns "
            "compact path/line/text matches and ignores build artifacts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Literal text to search for, e.g. 'SensitiveDetector'.",
                },
                "glob": {
                    "type": "string",
                    "description": "Relative glob to limit search scope, e.g. 'src/*.cc'.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum matches to return (optional, default 50).",
                },
            },
            "required": ["pattern"],
        },
    },
}

RUN_BASH: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "run_bash",
        "description": (
            "Run a shell command inside the project directory. Returns stdout, "
            "stderr, and exit_code. Use for grep/diff/inspect. Prefer "
            "build_project for compile cycles. Output is truncated."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to run."},
                "timeout": {"type": "integer", "description": "Timeout seconds (optional, default 120)."},
            },
            "required": ["command"],
        },
    },
}

BUILD_PROJECT: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "build_project",
        "description": (
            "Configure (cmake) and build (make) the Geant4 project. Returns "
            "structured success/errors with the compiler output. Call this to "
            "verify edits compile."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "threads": {"type": "integer", "description": "make -j threads (optional, default 4)."},
            },
            "required": [],
        },
    },
}

RUN_SMOKE: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "run_smoke",
        "description": (
            "Build then run a small smoke simulation to verify the project "
            "executes end-to-end. Call once the build succeeds to confirm "
            "runtime correctness."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "events": {"type": "integer", "description": "Number of events (optional, default small smoke count)."},
            },
            "required": [],
        },
    },
}

ALL_TOOL_SCHEMAS: list[dict[str, Any]] = [
    READ_FILE,
    EDIT_FILE,
    WRITE_FILE,
    LIST_FILES,
    SEARCH_TEXT,
    RUN_BASH,
    BUILD_PROJECT,
    RUN_SMOKE,
]
