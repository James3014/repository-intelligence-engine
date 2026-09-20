"""Read-only Python pattern-observation collector for Repository Intelligence.

This adapter owns Python source parsing (it is the source parser, not the
canonical engine). It emits only normalized, deterministic observations that
the canonical structured-facts engine classifies. It never decides review
outcomes and never approves, merges, releases, or executes reviewed source.

All detectors are syntax/literal based with no runtime evaluation. Detector
decisions stay advisory.
"""
from __future__ import annotations

import ast
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from repository_intelligence.contracts import RepositoryFactKind

DETECTOR_LANGUAGE = "python"
DETECTOR_VERSION = "python-ast-v1"

LOCALHOST_MARKERS = frozenset({"127.0.0.1", "0.0.0.0", "localhost", "::1", "[::1]"})
LOCALHOST_HOSTS = frozenset({"127.0.0.1", "0.0.0.0", "localhost", "::1"})

SUBPROCESS_CALLS = frozenset(
    {
        "subprocess.run",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.Popen",
        "subprocess.create_subprocess_exec",
        "subprocess.create_subprocess_shell",
        "subprocess.getoutput",
        "subprocess.getstatusoutput",
    }
)
OS_SPAWN_CALLS = frozenset(
    {
        "os.system",
        "os.popen",
        "os.spawnl",
        "os.spawnle",
        "os.spawnlp",
        "os.spawnlpe",
        "os.spawnv",
        "os.spawnve",
        "os.spawnvp",
        "os.spawnvpe",
    }
)

DETECTOR_COVERAGE: dict[str, bool] = {
    RepositoryFactKind.EMPTY_EXCEPTION_HANDLER.value: True,
    RepositoryFactKind.BROAD_EXCEPTION_HANDLER.value: True,
    RepositoryFactKind.SUBPROCESS_CALL.value: True,
    RepositoryFactKind.NETWORK_ENDPOINT_ADDED.value: False,
    RepositoryFactKind.VISIBLE_AUTH_CHECK.value: False,
    RepositoryFactKind.RELATED_TEST_CHANGED.value: False,
    RepositoryFactKind.HARDCODED_LOCALHOST.value: True,
    RepositoryFactKind.SILENT_RETRY_PATTERN.value: True,
}


def _safe_path(path: str) -> str | None:
    if not path or "\x00" in path or "\\" in path or path.startswith("/"):
        return None
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return path


def _build_alias_map(tree: ast.Module) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    seen: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for entry in node.names:
                name = entry.name
                asname = entry.asname or name.split(".", 1)[0]
                key = (name, asname)
                if key not in seen:
                    seen.add(key)
                    alias_map[asname] = name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for entry in node.names:
                if entry.name == "*" or not (entry.name.isidentifier()):
                    continue
                name = f"{module}.{entry.name}" if module else entry.name
                asname = entry.asname or entry.name
                key = (name, asname)
                if key not in seen:
                    seen.add(key)
                    alias_map[asname] = name
    return alias_map


def _resolve_callee(node: ast.AST, alias_map: Mapping[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return alias_map.get(node.id)
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        current: ast.AST = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            return None
        base = alias_map.get(current.id)
        if not base:
            return None
        parts.append(base)
        return ".".join(reversed(parts))
    return None


def _is_ellipsis_expr(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and node.value.value is Ellipsis
    )


def _is_silent_stmt(node: ast.AST) -> bool:
    return isinstance(node, (ast.Pass, ast.Break, ast.Continue)) or _is_ellipsis_expr(node)


def _handler_is_single_empty(node: ast.excepthandler) -> bool:
    return len(node.body) == 1 and (
        isinstance(node.body[0], ast.Pass) or _is_ellipsis_expr(node.body[0])
    )


def _handler_is_silent(node: ast.excepthandler) -> bool:
    return bool(node.body) and all(_is_silent_stmt(stmt) for stmt in node.body)


def _broad_handler_kind(node: ast.excepthandler) -> str | None:
    if node.type is None:
        return "bare_except_handler"
    if isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}:
        return "broad_except_handler"
    return None


def _string_literal_is_localhost(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if value in LOCALHOST_MARKERS:
        return True
    if "://" in value:
        try:
            hostname = urlsplit(value).hostname
        except ValueError:
            return False
        if hostname is None:
            return False
        host = hostname.strip("[]").lower()
        if host in LOCALHOST_HOSTS:
            return True
    return False


def _collect_detector_observations(
    tree: ast.Module, path: str
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int, str]] = set()

    def observe(
        fact_kind: str, line: int, column: int, evidence_ref: str
    ) -> None:
        key = (fact_kind, line, column, evidence_ref)
        if key in seen:
            return
        seen.add(key)
        observations.append(
            {
                "fact_kind": fact_kind,
                "file_path": path,
                "line": line,
                "column": column,
                "evidence_ref": evidence_ref,
            }
        )

    alias_map = _build_alias_map(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if _handler_is_single_empty(node):
                observe(
                    RepositoryFactKind.EMPTY_EXCEPTION_HANDLER.value,
                    node.lineno,
                    node.col_offset,
                    "empty_except_handler",
                )
            broad_kind = _broad_handler_kind(node)
            if broad_kind is not None:
                observe(
                    RepositoryFactKind.BROAD_EXCEPTION_HANDLER.value,
                    node.lineno,
                    node.col_offset,
                    broad_kind,
                )
            continue

        if isinstance(node, ast.Call):
            resolved = _resolve_callee(node.func, alias_map)
            if resolved in SUBPROCESS_CALLS:
                observe(
                    RepositoryFactKind.SUBPROCESS_CALL.value,
                    node.lineno,
                    node.col_offset,
                    f"subprocess_call:{resolved}",
                )
            elif resolved in OS_SPAWN_CALLS:
                observe(
                    RepositoryFactKind.SUBPROCESS_CALL.value,
                    node.lineno,
                    node.col_offset,
                    f"subprocess_call:{resolved}",
                )
            continue

        if isinstance(node, ast.Constant) and _string_literal_is_localhost(node.value):
            observe(
                RepositoryFactKind.HARDCODED_LOCALHOST.value,
                node.lineno,
                node.col_offset,
                "hardcoded_localhost",
            )
            continue

    for loop in ast.walk(tree):
        if not isinstance(loop, (ast.For, ast.While)):
            continue
        for body_node in ast.walk(loop):
            if body_node is loop:
                continue
            if not isinstance(body_node, ast.Try):
                continue
            for handler in body_node.handlers:
                if _handler_is_silent(handler):
                    if _handler_is_single_empty(handler):
                        ref = "silent_retry_try_except_pass"
                    else:
                        ref = "silent_retry_handler"
                    observe(
                        RepositoryFactKind.SILENT_RETRY_PATTERN.value,
                        handler.lineno,
                        handler.col_offset,
                        ref,
                    )

    return observations


def collect_python_pattern_observations(
    source_files: Mapping[str, str],
) -> dict[str, Any]:
    """Collect normalized deterministic pattern observations from Python source.

    ``source_files`` maps repository-relative paths to full source text. Only
    successfully parsed files are reported as covered; parse failures fail the
    collection closed rather than silently dropping a file.

    Returns the normalized observation bundle consumed by
    ``repository_intelligence.facts.analyze_structured_facts``.
    """
    if not isinstance(source_files, Mapping):
        raise TypeError("source_files must be a mapping of path to source text")

    covered_files: list[str] = []
    collection_errors: list[str] = []
    observations: list[dict[str, Any]] = []

    for raw_path, source in source_files.items():
        path = _safe_path(str(raw_path))
        if path is None:
            collection_errors.append(f"invalid repository path: {raw_path!r}")
            continue
        if not isinstance(source, str):
            collection_errors.append(f"{path}: source must be a string")
            continue
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            collection_errors.append(f"{path}: {exc.msg} (line {exc.lineno})")
            continue
        covered_files.append(path)
        observations.extend(_collect_detector_observations(tree, path))

    covered_files = sorted(set(covered_files))

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in observations:
        key = "|".join(
            str(item.get(k)) for k in ("fact_kind", "file_path", "line", "column", "evidence_ref")
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    deduped.sort(
        key=lambda item: (
            item["fact_kind"],
            item["file_path"],
            item["line"],
            item["column"],
            item["evidence_ref"],
        )
    )

    return {
        "language": DETECTOR_LANGUAGE,
        "detector_version": DETECTOR_VERSION,
        "covered_files": covered_files,
        "observations": deduped,
        "detector_coverage": dict(DETECTOR_COVERAGE),
        "collection_complete": not bool(collection_errors),
        "collection_errors": sorted(set(collection_errors)),
    }


__all__ = [
    "DETECTOR_LANGUAGE",
    "DETECTOR_VERSION",
    "DETECTOR_COVERAGE",
    "collect_python_pattern_observations",
]