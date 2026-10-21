"""Regression: ``import a.b`` binds the top-level name ``a`` (issue 113)."""

from __future__ import annotations

from adapters.python_fact_detector import collect_python_pattern_observations


def _subprocess_calls(src: str) -> list[tuple[str, int]]:
    observations = collect_python_pattern_observations({"x.py": src})["observations"]
    return sorted(
        (item["evidence_ref"], item["line"])
        for item in observations
        if item["fact_kind"] == "SUBPROCESS_CALL"
    )


def test_plain_import_os_reports_os_system() -> None:
    assert _subprocess_calls("import os\nos.system('ls')\n") == [
        ("subprocess_call:os.system", 2)
    ]


def test_import_os_then_os_path_still_reports_os_system() -> None:
    src = "import os\nimport os.path\nos.system('ls')\n"
    assert _subprocess_calls(src) == [("subprocess_call:os.system", 3)]


def test_import_os_path_then_os_still_reports_os_system() -> None:
    src = "import os.path\nimport os\nos.system('ls')\n"
    assert _subprocess_calls(src) == [("subprocess_call:os.system", 3)]


def test_import_os_path_alone_reports_os_system() -> None:
    src = "import os.path\nos.system('ls')\n"
    assert _subprocess_calls(src) == [("subprocess_call:os.system", 2)]


def test_import_os_path_alone_reports_os_popen() -> None:
    src = "import os.path\nos.popen('ls')\n"
    assert _subprocess_calls(src) == [("subprocess_call:os.popen", 2)]


def test_import_subprocess_submodule_style_reports_subprocess_run() -> None:
    src = "import subprocess\nimport os.path\nsubprocess.run(['ls'])\n"
    assert _subprocess_calls(src) == [("subprocess_call:subprocess.run", 3)]


def test_aliased_os_path_does_not_make_alias_look_like_os() -> None:
    src = "import os.path as p\np.system('ls')\n"
    assert _subprocess_calls(src) == []


def test_aliased_os_path_does_not_hide_real_os_system() -> None:
    src = "import os.path as p\nimport os\nos.system('ls')\np.system('ls')\n"
    assert _subprocess_calls(src) == [("subprocess_call:os.system", 3)]
