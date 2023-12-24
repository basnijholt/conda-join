"""unidep - Unified Conda and Pip requirements management.

This module provides utility functions used throughout the package.
"""
from __future__ import annotations

import codecs
import platform
import re
import sys
import warnings
from pathlib import Path
from typing import NamedTuple, cast

from unidep._version import __version__
from unidep.platform_definitions import (
    PEP508_MARKERS,
    VALID_SELECTORS,
    Platform,
    Selector,
    platforms_from_selector,
    validate_selector,
)


def add_comment_to_file(
    filename: str | Path,
    extra_lines: list[str] | None = None,
) -> None:
    """Add a comment to the top of a file."""
    if extra_lines is None:
        extra_lines = []
    with open(filename, "r+") as f:  # noqa: PTH123
        content = f.read()
        f.seek(0, 0)
        command_line_args = " ".join(sys.argv[1:])
        txt = [
            f"# This file is created and managed by `unidep` {__version__}.",
            "# For details see https://github.com/basnijholt/unidep",
            f"# File generated with: `unidep {command_line_args}`",
            *extra_lines,
        ]
        content = "\n".join(txt) + "\n\n" + content
        f.write(content)


def remove_top_comments(filename: str | Path) -> None:
    """Removes the top comments (lines starting with '#') from a file."""
    with open(filename) as file:  # noqa: PTH123
        lines = file.readlines()

    first_non_comment = next(
        (i for i, line in enumerate(lines) if not line.strip().startswith("#")),
        len(lines),
    )
    content_without_comments = lines[first_non_comment:]
    with open(filename, "w") as file:  # noqa: PTH123
        file.writelines(content_without_comments)


def escape_unicode(string: str) -> str:
    """Escape unicode characters."""
    return codecs.decode(string, "unicode_escape")


def is_pip_installable(folder: str | Path) -> bool:  # pragma: no cover
    """Determine if the project is pip installable.

    Checks for existence of setup.py or [build-system] in pyproject.toml.
    """
    path = Path(folder)
    if (path / "setup.py").exists():
        return True

    # When toml makes it into the standard library, we can use that instead
    # For now this is good enough, except it doesn't handle the case where
    # [build-system] is inside of a multi-line literal string.
    pyproject_path = path / "pyproject.toml"
    if pyproject_path.exists():
        with pyproject_path.open("r") as file:
            for line in file:
                if line.strip().startswith("[build-system]"):
                    return True
    return False


def identify_current_platform() -> Platform:
    """Detect the current platform."""
    system = platform.system().lower()
    architecture = platform.machine().lower()

    if system == "linux":
        if architecture == "x86_64":
            return "linux-64"
        if architecture == "aarch64":
            return "linux-aarch64"
        if architecture == "ppc64le":
            return "linux-ppc64le"
        msg = "Unsupported Linux architecture"
        raise ValueError(msg)
    if system == "darwin":
        if architecture == "x86_64":
            return "osx-64"
        if architecture == "arm64":
            return "osx-arm64"
        msg = "Unsupported macOS architecture"
        raise ValueError(msg)
    if system == "windows":
        if "64" in architecture:
            return "win-64"
        msg = "Unsupported Windows architecture"
        raise ValueError(msg)
    msg = "Unsupported operating system"
    raise ValueError(msg)


def build_pep508_environment_marker(
    platforms: list[Platform | tuple[Platform, ...]],
) -> str:
    """Generate a PEP 508 selector for a list of platforms."""
    sorted_platforms = tuple(sorted(platforms))
    if sorted_platforms in PEP508_MARKERS:
        return PEP508_MARKERS[sorted_platforms]  # type: ignore[index]
    environment_markers = [
        PEP508_MARKERS[platform]
        for platform in sorted(sorted_platforms)
        if platform in PEP508_MARKERS
    ]
    return " or ".join(environment_markers)


class ParsedPackageStr(NamedTuple):
    """A package name and version pinning."""

    name: str
    pin: str | None = None
    # Only populated when parsing a package_str like "numpy >=1.18.1:linux64".
    selector: Selector | None = None


def parse_package_str(package_str: str) -> ParsedPackageStr:
    """Splits a string into package name, version pinning, and platform selector."""
    # Regex to match package name, version pinning, and optionally platform selector
    name_pattern = r"[a-zA-Z0-9_-]+"
    version_pin_pattern = r".*?"
    selector_pattern = r"[a-zA-Z0-9]+"
    pattern = rf"({name_pattern})\s*({version_pin_pattern})?(:({selector_pattern}))?$"
    match = re.match(pattern, package_str)

    if match:
        package_name = match.group(1).strip()
        version_pin = match.group(2).strip() if match.group(2) else None
        selector = cast(Selector, match.group(4).strip()) if match.group(4) else None

        if selector is not None:
            validate_selector(selector)

        return ParsedPackageStr(
            package_name,
            version_pin,
            selector,
        )

    msg = f"Invalid package string: '{package_str}'"
    raise ValueError(msg)


def _simple_warning_format(
    message: Warning | str,
    category: type[Warning],  # noqa: ARG001
    filename: str,
    lineno: int,
    line: str | None = None,  # noqa: ARG001
) -> str:  # pragma: no cover
    """Format warnings without code context."""
    return (
        f"---------------------\n"
        f"⚠️  *** WARNING *** ⚠️\n"
        f"{message}\n"
        f"Location: {filename}:{lineno}\n"
        f"---------------------\n"
    )


def warn(
    message: str | Warning,
    category: type[Warning] = UserWarning,
    stacklevel: int = 1,
) -> None:
    """Emit a warning with a custom format specific to this package."""
    original_format = warnings.formatwarning
    warnings.formatwarning = _simple_warning_format
    try:
        warnings.warn(message, category, stacklevel=stacklevel + 1)
    finally:
        warnings.formatwarning = original_format


def selector_from_comment(comment: str) -> str | None:
    """Extract a valid selector from a comment."""
    multiple_brackets_pat = re.compile(r"#.*\].*\[")  # Detects multiple brackets
    if multiple_brackets_pat.search(comment):
        msg = f"Multiple bracketed selectors found in comment: '{comment}'"
        raise ValueError(msg)

    sel_pat = re.compile(r"#\s*\[([^\[\]]+)\]")
    m = sel_pat.search(comment)
    if not m:
        return None
    selectors = m.group(1).strip().split()
    valid = [s in VALID_SELECTORS for s in selectors]
    if not all(valid):
        msg = (
            f"Unsupported platform specifier: '{comment}' use one of {VALID_SELECTORS}"
        )
        raise ValueError(msg)
    return " ".join(selectors)


def extract_matching_platforms(comment: str) -> list[Platform]:
    """Get all platforms matching a comment."""
    selector = selector_from_comment(comment)
    if selector is None:
        return []
    return platforms_from_selector(selector)
