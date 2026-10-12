"""Characterize canonical evidence identities before and after de-duplication."""

from __future__ import annotations

import unittest

from adapters.github_action import _hash_payload as adapter_hash
from repository_intelligence._hashing import content_hash, hash_payload
from repository_intelligence.cfi import _content_hash as cfi_hash
from repository_intelligence.core import _content_hash as core_hash
from repository_intelligence.eia import _content_hash as eia_hash
from repository_intelligence.facts import _content_hash as facts_hash
from repository_intelligence.guard_delta import _hash_payload as guard_delta_hash
from repository_intelligence.impact import _content_hash as impact_hash
from repository_intelligence.knowledge import _hash_payload as knowledge_hash
from repository_intelligence.retrieval import _content_hash as retrieval_hash

ALL_HASHERS = (
    content_hash, hash_payload, adapter_hash, cfi_hash, core_hash, eia_hash,
    facts_hash, guard_delta_hash, impact_hash, knowledge_hash, retrieval_hash,
)


class TestCanonicalContentHash(unittest.TestCase):
    def test_historical_hashes_are_byte_identical(self) -> None:
        examples = (
            ({}, "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"),
            (
                {"alpha": "é", "content_sha256": "ignored", "z": [1, None, False]},
                "db6107e88e52170a029d787a6c3bd9f7fea4025c90cab685fdc9e5880fbca155",
            ),
            (
                {"list": [3, 2, 1], "x": {"b": 2, "a": 1}},
                "be1c6db805596e6dd760c8f619176d5f48bd9bbfaa273ad63d1ddab96c33e384",
            ),
        )
        for hasher in ALL_HASHERS:
            for payload, expected in examples:
                with self.subTest(hasher=hasher, payload=payload):
                    self.assertEqual(hasher(payload), expected)

    def test_self_hash_exclusion_preserved_and_tamper_changes_identity(self) -> None:
        payload = {"x": {"a": 1}, "content_sha256": "old"}
        replaced_hash = {"x": {"a": 1}, "content_sha256": "new"}
        tampered_payload = {"x": {"a": 2}, "content_sha256": "old"}
        for hasher in ALL_HASHERS:
            with self.subTest(hasher=hasher):
                self.assertEqual(hasher(payload), hasher(replaced_hash))
                self.assertNotEqual(hasher(payload), hasher(tampered_payload))

    def test_all_legacy_helpers_use_one_shared_implementation(self) -> None:
        for hasher in (cfi_hash, core_hash, eia_hash, facts_hash, impact_hash, retrieval_hash):
            self.assertIs(hasher, content_hash)
        for hasher in (adapter_hash, guard_delta_hash, knowledge_hash):
            self.assertIs(hasher, hash_payload)

    def test_additional_exclusion_must_be_explicit(self) -> None:
        payload = {"x": 1, "volatile": "ignored", "content_sha256": "ignored"}
        self.assertEqual(
            hash_payload(payload, exclude=("content_sha256", "volatile")),
            content_hash({"x": 1}),
        )
        self.assertNotEqual(hash_payload(payload), content_hash({"x": 1}))


if __name__ == "__main__":
    unittest.main()
