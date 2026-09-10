import pytest
from repository_intelligence import core as ri
from adapters.github_action import _validate_repo


@pytest.mark.parametrize(
    "invalid_repo",
    [
        " owner/repo ",
        "owner /repo",
        "owner/ repo",
        "ow ner/repo",
        "owner/re po",
        "owner\n/repo",
        "owner/repo\t",
        "owner\x00/repo",
        "/repo",
        "owner/",
        "owner//repo",
        "owner/repo/sub",
        "owner",
        "",
        "owner/repo@123",
        "owner/repo$",
    ],
)
def test_core_rejects_noncanonical_repository_identity(invalid_repo: str):
    rev = ri.revision_identity({
        "repository": invalid_repo,
        "pr_number": 1,
        "head_sha": "h123",
        "base_sha": "b123",
        "current_main_sha": "b123",
    })
    assert rev.is_valid is False
    assert "repository domain or format invalid" in rev.evidence_gaps


@pytest.mark.parametrize(
    "valid_repo",
    [
        "owner/repo",
        "Owner-Name/Repo-Name",
        "owner.name_123/repo.name-456",
        "org_1/project-2.core",
    ],
)
def test_core_and_adapter_accept_canonical_repository_identity(valid_repo: str):
    rev = ri.revision_identity({
        "repository": valid_repo,
        "pr_number": 1,
        "head_sha": "h123",
        "base_sha": "b123",
        "current_main_sha": "b123",
    })
    assert rev.is_valid is True
    assert rev.repository == valid_repo
    assert _validate_repo(valid_repo) == valid_repo


@pytest.mark.parametrize(
    "invalid_repo",
    [
        " owner/repo ",
        "owner /repo",
        "owner/ repo",
        "ow ner/repo",
        "owner/re po",
        "owner\n/repo",
        "owner/repo\t",
        "/repo",
        "owner/",
        "owner//repo",
        "owner/repo/sub",
        "",
    ],
)
def test_core_and_adapter_agree_on_rejection(invalid_repo: str):
    rev = ri.revision_identity({
        "repository": invalid_repo,
        "pr_number": 1,
        "head_sha": "h123",
        "base_sha": "b123",
        "current_main_sha": "b123",
    })
    assert rev.is_valid is False
    with pytest.raises(ValueError, match="repository must be owner/name"):
        _validate_repo(invalid_repo)
