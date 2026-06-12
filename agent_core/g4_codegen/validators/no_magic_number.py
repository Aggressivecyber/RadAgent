"""No Magic Number Validator — detects hardcoded physical constants in generated C++.

Physical values (dimensions, energies, densities) must come from Model IR
via named constants, not hardcoded as numeric literals in expressions.
"""

from __future__ import annotations

import re
from typing import Any

# Numeric literal pattern — used in check_magic_numbers() for line-by-line scanning.
# Comment / constant-definition filtering is handled inline in that function,
# not via regex lookbehind (Python re does not support variable-width lookbehind).
_NUMERIC_RE = re.compile(r"(\d+\.?\d*)")

# Known safe values that are NOT magic numbers
SAFE_VALUES = {
    "0",
    "1",
    "-1",
    "2",
    "0.",
    "1.",
    "2.",
    "0.0",
    "1.0",
    "2.0",
    "0.5",
    "360",
    "180",
    "100",
}

# CLHEP unit suffixes that make a number acceptable
CLHEP_UNITS = {
    "nm",
    "um",
    "mm",
    "cm",
    "m",
    "km",
    "MeV",
    "keV",
    "GeV",
    "eV",
    "g",
    "mg",
    "deg",
    "rad",
    "ns",
    "s",
    "Gy",
    "gray",
}

# Keywords indicating constant definitions (allowed)
CONST_KEYWORDS = {"const", "constexpr", "define", "enum", "static const"}

PRESENTATION_CONTEXTS = ("G4Colour", "G4VisAttributes", "SetScreenSize", "std::setw")


def check_magic_numbers(code: str, module_id: str = "?") -> tuple[bool, list[str]]:
    """Check C++ code for magic numbers.

    Returns (is_clean, list_of_violations).
    """
    if not code.strip():
        return True, []

    violations: list[str] = []
    lines = code.split("\n")

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()

        # Skip comments and preprocessor directives
        if stripped.startswith("//") or stripped.startswith("#"):
            continue
        if stripped.startswith("*") or stripped.startswith("/*"):
            continue

        if any(token in stripped for token in PRESENTATION_CONTEXTS):
            continue

        # Skip lines that are constant definitions
        if any(kw in stripped for kw in CONST_KEYWORDS):
            continue

        stripped = _strip_inline_comment(stripped)

        # Find all numeric literals
        for match in re.finditer(r"(\d+\.?\d*)", stripped):
            value = match.group(1)
            if value in SAFE_VALUES:
                continue

            # Skip if inside an identifier (e.g., G4Box → the "4" is part of a name)
            start = match.start()
            if start > 0 and (stripped[start - 1].isalpha() or stripped[start - 1] == "_"):
                continue
            end = match.end()
            if end < len(stripped) and (stripped[end].isalpha() or stripped[end] == "_"):
                continue

            # Check if followed by a CLHEP unit (e.g., 10*mm)
            pos = match.end()
            remaining = stripped[pos:].lstrip()
            if remaining.startswith("*"):
                after_star = remaining[1:].lstrip()
                if any(after_star.startswith(unit) for unit in CLHEP_UNITS):
                    continue  # e.g., 10*mm — acceptable

            # Skip if it's part of a string
            before = stripped[: match.start()]
            if before.count('"') % 2 == 1:
                continue  # inside a string literal

            # This looks like a magic number
            violations.append(
                f"{module_id}:{line_num}: magic number '{value}' in '{stripped[:80]}'"
            )

    is_clean = len(violations) == 0
    return is_clean, violations


def validate_no_magic_numbers(modules: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """Validate all modules are free of magic numbers."""
    all_violations: list[str] = []
    all_clean = True

    for mod in modules:
        code = mod.get("code", "")
        module_id = mod.get("module_id", "?")

        clean, violations = check_magic_numbers(code, module_id)
        if not clean:
            all_clean = False
            all_violations.extend(violations)

    return all_clean, all_violations


def _strip_inline_comment(line: str) -> str:
    in_string = False
    escaped = False
    for index, char in enumerate(line):
        if char == "\\" and in_string:
            escaped = not escaped
            continue
        if char == '"' and not escaped:
            in_string = not in_string
        escaped = False
        if not in_string and line[index : index + 2] == "//":
            return line[:index].rstrip()
    return line
