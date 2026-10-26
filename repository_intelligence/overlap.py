from .models import Disposition


def detect(items):
    eligible_before = {
        id(classification): classification.disposition == Disposition.REVIEW_READY
        for classification in items
    }
    for index, left in enumerate(items):
        for right in items[index + 1 :]:
            paths = sorted(set(left.snapshot.changed_files) & set(right.snapshot.changed_files))
            if paths:
                left.overlaps[right.snapshot.pr_number] = paths
                right.overlaps[left.snapshot.pr_number] = paths
                for classification, other in ((left, right), (right, left)):
                    if "PATH_OVERLAP" not in classification.findings:
                        classification.findings.append("PATH_OVERLAP")
                        classification.reasons.append(
                            f"overlaps PR {other.snapshot.pr_number}"
                        )
                if eligible_before[id(left)] and eligible_before[id(right)]:
                    left.disposition = Disposition.WAIT_REBIND
                    right.disposition = Disposition.WAIT_REBIND

    issues = {}
    for classification in items:
        for issue_number in set(classification.snapshot.issue_numbers or ()):
            issues.setdefault(issue_number, {})[id(classification)] = classification

    for issue_prs in issues.values():
        classifications = list(issue_prs.values())
        if len(classifications) > 1:
            for classification in classifications:
                if "SAME_ISSUE_CHAIN" not in classification.findings:
                    classification.findings.append("SAME_ISSUE_CHAIN")
                    classification.reasons.append("multiple active PRs share an Issue")
            eligible = [
                classification
                for classification in classifications
                if eligible_before[id(classification)]
            ]
            if len(eligible) > 1:
                for classification in eligible:
                    classification.disposition = Disposition.WAIT_REBIND
