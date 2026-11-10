import unittest
from dataclasses import FrozenInstanceError
from datetime import timedelta, timezone
from uuid import UUID

from practice.models import (
    ActivityType,
    CodingProblem,
    Collection,
    Difficulty,
    Exercise,
    Flashcard,
    Outcome,
    OverrideKind,
    ReviewOverride,
    Timing,
    validate_membership,
)
from practice.tests.helpers import COLLECTION, ITEM, OWNER, START, attempt, item


class ContractTests(unittest.TestCase):
    def test_content_is_typed_not_flashcard_shaped(self):
        for content, expected in (
            (CodingProblem("https://example.org/problem/1"), ActivityType.CODING_PROBLEM),
            (Flashcard("Question", "Answer"), ActivityType.FLASHCARD),
            (Exercise("Explain the invariant without notes"), ActivityType.EXERCISE),
        ):
            self.assertEqual(item(content=content).activity_type, expected)

    def test_urls_and_difficulty(self):
        for url in (
            "http://example.org",
            "javascript:alert(1)",
            "https://user:pass@example.org",
            "https:///missing-host",
            "https://example.org:bad/",
            "https://example.org:0/",
            "https://example.org/ space",
            "https://example.org/\n",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                CodingProblem(url)
        with self.assertRaises(ValueError):
            CodingProblem("https://example.org", "medium")
        self.assertEqual(
            CodingProblem("https://example.org", Difficulty.HARD).difficulty, Difficulty.HARD
        )

    def test_invalid_records_and_mutable_inputs(self):
        for changes in (
            {"title": " "},
            {"id": "not-a-uuid"},
            {"content": {}},
            {"archived": 1},
            {"target_seconds": True},
            {"tags": "arrays"},
            {"tags": [""]},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                item(**changes)
        tags = ["arrays"]
        record = item(tags=tags)
        tags.append("graphs")
        self.assertEqual(record.tags, ("arrays",))
        with self.assertRaises(FrozenInstanceError):
            record.archived = True

    def test_utc_normalization_and_naive_rejection(self):
        offset = timezone(timedelta(hours=5))
        self.assertEqual(item(created_at=START.astimezone(offset)).created_at, START)
        for constructor in (
            lambda: item(created_at=START.replace(tzinfo=None)),
            lambda: attempt(1, occurred_at=START.replace(tzinfo=None)),
        ):
            with self.assertRaises(ValueError):
                constructor()

    def test_collection_ownership(self):
        collection = Collection(COLLECTION, OWNER, "Practice")
        validate_membership(collection, item())
        with self.assertRaises(ValueError):
            validate_membership(Collection(COLLECTION, UUID(int=99), "Other"), item())
        with self.assertRaises(ValueError):
            validate_membership(Collection(UUID(int=99), OWNER, "Other"), item())

    def test_timing_preserves_measurement_and_correction(self):
        timing = Timing(
            measured_seconds=2400,
            corrected_seconds=1800,
            correction_reason="Forgot to pause during a break",
        )
        self.assertEqual(timing.measured_seconds, 2400)
        self.assertEqual(timing.effective_seconds, 1800)
        self.assertEqual(timing.source, "corrected")
        self.assertIsNone(Timing().effective_seconds)
        self.assertEqual(Timing().source, "missing")
        self.assertEqual(Timing(corrected_seconds=60).source, "manual")
        self.assertEqual(Timing(measured_seconds=60).source, "measured")
        self.assertEqual(Timing(measured_seconds=60, corrected_seconds=0).effective_seconds, 0)

    def test_invalid_timing_and_confidence(self):
        for duration in (-1, float("nan"), float("inf"), True, "60"):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                Timing(measured_seconds=duration)
        with self.assertRaises(ValueError):
            Timing(correction_reason="orphan reason")
        for confidence in (0, 6, True, 1.5, "5"):
            with self.assertRaises(ValueError):
                attempt(1, confidence=confidence)
        with self.assertRaises(ValueError):
            attempt(1, outcome="independent")
        self.assertEqual(attempt(1, outcome=Outcome.INDEPENDENT, confidence=5).confidence, 5)

    def test_override_contract(self):
        arguments = dict(
            id=UUID(int=50),
            owner_id=OWNER,
            item_id=ITEM,
            requested_at=START,
            due_at=START,
            kind=OverrideKind.REVIEW_SOONER,
        )
        self.assertEqual(ReviewOverride(**arguments).due_at, START)
        with self.assertRaises(ValueError):
            ReviewOverride(**(arguments | {"due_at": START - timedelta(seconds=1)}))
        with self.assertRaises(ValueError):
            ReviewOverride(**(arguments | {"kind": "snooze"}))


if __name__ == "__main__":
    unittest.main()
