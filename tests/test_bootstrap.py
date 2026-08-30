from __future__ import annotations

import ast
from pathlib import Path

import repository_intelligence as ri
import repository_intelligence.cfi as cfi
import repository_intelligence.classifier as classifier
import repository_intelligence.contracts as contracts
import repository_intelligence.core as core
import repository_intelligence.eia as eia
import repository_intelligence.impact as impact
import repository_intelligence.models as models
import repository_intelligence.overlap as overlap


def test_importability_all_modules():
    assert ri is not None
    assert models is not None
    assert classifier is not None
    assert overlap is not None
    assert contracts is not None
    assert core is not None
    assert impact is not None
    assert cfi is not None
    assert eia is not None


def test_public_v1_1_operations():
    expected_ops = [
        "revision_identity",
        "classify_readiness",
        "analyze_cross_pr_overlap",
        "fingerprint_ci_failures",
        "verify_ci_failure_evidence",
        "analyze_change_impact",
        "verify_change_impact_report",
        "analyze_ci_failure_intelligence",
        "verify_ci_failure_intelligence_report",
        "plan_external_intelligence_automation",
        "verify_external_intelligence_automation_envelope",
        "build_repository_intelligence_report",
        "verify_repository_intelligence_report",
    ]
    for op in expected_ops:
        assert hasattr(ri, op), f"Missing operation {op} in repository_intelligence"
        assert callable(getattr(ri, op)), f"{op} is not callable"


def test_claim_ceiling_constants():
    assert ri.CLAIM_CEILING == "PR_INTELLIGENCE_ONLY"
    assert ri.CI_EVIDENCE_CLAIM_CEILING == "CI_EVIDENCE_ONLY"
    assert contracts.CLAIM_CEILING == "PR_INTELLIGENCE_ONLY"
    assert contracts.CI_EVIDENCE_CLAIM_CEILING == "CI_EVIDENCE_ONLY"


def test_no_reviewer_imports_under_repository_intelligence():
    pkg_dir = Path(__file__).resolve().parent.parent / "repository_intelligence"
    violations = []
    for path in sorted(pkg_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("reviewer"):
                violations.append(f"{path.name}:{node.lineno}:{node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("reviewer"):
                        violations.append(f"{path.name}:{node.lineno}:{alias.name}")
    assert violations == [], f"Found reviewer.* imports in canonical package: {violations}"


def test_absence_of_application_modules():
    repo_root = Path(__file__).resolve().parent.parent
    pkg_dir = repo_root / "repository_intelligence"

    forbidden_module_stems = {
        "semantic",
        "opencli",
        "publication",
        "service",
        "queue",
        "receipt",
        "collector",
        "github",
        "github_action",
        "attempt",
        "render",
        "scan",
        "status",
        "unattended",
        "webmcp",
        "intelligence_cli",
        "service_cli",
    }

    # Verify no forbidden files exist in package or root
    found_in_pkg = {p.stem for p in pkg_dir.glob("*.py")}
    assert not (found_in_pkg & forbidden_module_stems), f"Forbidden modules found in package: {found_in_pkg & forbidden_module_stems}"

    found_in_root = {p.stem for p in repo_root.glob("*.py")}
    assert not (found_in_root & forbidden_module_stems), f"Forbidden modules found in root: {found_in_root & forbidden_module_stems}"
