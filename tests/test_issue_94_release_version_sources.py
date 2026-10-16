"""Release version sources must agree (Issue #94). Read-only: parses files, edits nothing.

Sources compared:
1. ``pyproject.toml`` ``version``.
2. README ``Current release: **`vX.Y.Z`**`` line and every install-example
   version (``repository-intelligence-engine[/terminal][.git]@vX.Y.Z``).
3. The top released ``CHANGELOG.md`` entry: the first ``## [X.Y.Z]`` heading that
   is not marked ``Unreleased`` or ``unpublished``.
4. The self-consumed action pin in ``.github/workflows/repository-intelligence.yml``,
   ``uses: James3014/repository-intelligence-engine@<40-hex sha>  # vX.Y.Z`` (or
   ``@vX.Y.Z``).  This pin may lag pyproject by one release by design, because it
   must reference an already-published tag.  It must therefore only be <= the
   pyproject version and name a dated (released) CHANGELOG entry.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ".github/workflows/repository-intelligence.yml"
SELF = "James3014/repository-intelligence-engine"


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(p) for p in text.split("."))


def pyproject_version(text: str) -> str:
    m = re.search(r'^version\s*=\s*"(\d+\.\d+\.\d+)"', text, re.M)
    assert m, "pyproject.toml version not found"
    return m.group(1)


def readme_current_release(text: str) -> str:
    m = re.search(r"^Current release:\s*\*\*`v(\d+\.\d+\.\d+)`\*\*", text, re.M)
    assert m, "README 'Current release' line not found"
    return m.group(1)


def readme_install_versions(text: str) -> list[str]:
    return re.findall(r"repository-intelligence-engine(?:/terminal)?(?:\.git)?@v(\d+\.\d+\.\d+)", text)


def changelog_entries(text: str) -> list[tuple[str, str]]:
    return re.findall(r"^## \[(\d+\.\d+\.\d+)\](.*)$", text, re.M)


def released_changelog_versions(text: str) -> list[str]:
    return [
        v
        for v, rest in changelog_entries(text)
        if re.search(r"\d{4}-\d{2}-\d{2}", rest) and not re.search(r"unreleased|unpublished", rest, re.I)
    ]


def workflow_pin_version(text: str) -> str:
    m = re.search(rf"uses:\s*{re.escape(SELF)}@(?:v(\d+\.\d+\.\d+)\b|[0-9a-f]{{40}}\s*#\s*v(\d+\.\d+\.\d+))", text)
    assert m, "self-consumed action pin not found"
    return m.group(1) or m.group(2)


def check(pyproject: str, readme: str, changelog: str, workflow: str) -> list[str]:
    """Return a list of disagreements (empty when consistent)."""
    problems: list[str] = []
    py = pyproject_version(pyproject)
    cur = readme_current_release(readme)
    if cur != py:
        problems.append(f"README current release {cur} != pyproject {py}")
    installs = readme_install_versions(readme)
    if not installs:
        problems.append("README has no install-example versions")
    for v in sorted(set(installs) - {py}):
        problems.append(f"README install example {v} != pyproject {py}")
    released = released_changelog_versions(changelog)
    if not released or released[0] != py:
        problems.append(f"top released CHANGELOG entry {released[:1]} != pyproject {py}")
    pin = workflow_pin_version(workflow)
    if _ver(pin) > _ver(py):
        problems.append(f"workflow pin {pin} is newer than pyproject {py}")
    if pin not in released:
        problems.append(f"workflow pin {pin} is not a dated CHANGELOG release")
    return problems


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _current() -> tuple[str, str, str, str]:
    return _read("pyproject.toml"), _read("README.md"), _read("CHANGELOG.md"), _read(WORKFLOW)


def test_release_version_sources_agree() -> None:
    assert check(*_current()) == []


def test_mutating_any_single_source_is_detected() -> None:
    pyproject, readme, changelog, workflow = _current()
    py = pyproject_version(pyproject)
    bumped = "9.9.9"
    cases = {
        "pyproject": (pyproject.replace(f'version = "{py}"', f'version = "{bumped}"', 1), readme, changelog, workflow),
        "readme current": (pyproject, readme.replace(f"**`v{py}`**", f"**`v{bumped}`**", 1), changelog, workflow),
        "readme install": (
            pyproject,
            readme.replace(f"{SELF}@v{py}", f"{SELF}@v{bumped}", 1),
            changelog,
            workflow,
        ),
        "changelog": (pyproject, readme, changelog.replace(f"## [{py}] - ", f"## [{py}] - Unreleased ", 1), workflow),
        "pin too new": (pyproject, readme, changelog, re.sub(r"(# v)\d+\.\d+\.\d+", r"\g<1>" + bumped, workflow, count=1)),
    }
    for name, args in cases.items():
        assert check(*args), f"mutation not detected: {name}"


def test_pin_lagging_one_release_is_allowed() -> None:
    pyproject, readme, changelog, workflow = _current()
    py = pyproject_version(pyproject)
    released = released_changelog_versions(changelog)
    older = [v for v in released if _ver(v) < _ver(py)]
    assert older, "need an older released version to model a lagging pin"
    lagging = re.sub(r"(# v)\d+\.\d+\.\d+", r"\g<1>" + older[0], workflow, count=1)
    assert check(pyproject, readme, changelog, lagging) == []


def test_parsers_accept_tag_pin_form() -> None:
    assert workflow_pin_version(f"uses: {SELF}@v1.2.3") == "1.2.3"
