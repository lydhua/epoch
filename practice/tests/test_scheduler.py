import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from practice.models import Difficulty, Outcome, OverrideKind, ReviewOverride, Timing
from practice.scheduler import DAY, LearningState, Policy, schedule
from practice.tests.helpers import ITEM, OWNER, START, attempt, item


class SchedulerTests(unittest.TestCase):
    def decide(self, history=(), *, record=None, policy=None, now=None, override=None):
        return schedule(
            item() if record is None else record,
            list(history),
            now=now or START + timedelta(days=400),
            policy=policy,
            override=override,
        )

    def override(self, *, requested_days, due_days, kind=OverrideKind.SNOOZE, **changes):
        values = dict(
            id=UUID(int=90),
            owner_id=OWNER,
            item_id=ITEM,
            requested_at=START + timedelta(days=requested_days),
            due_at=START + timedelta(days=due_days),
            kind=kind,
        )
        return ReviewOverride(**(values | changes))

    def test_new_item_is_due_without_read_time_rescheduling(self):
        decision = self.decide()
        self.assertEqual(decision.state, LearningState.LEARNING)
        self.assertEqual(decision.next_due_at, START)
        self.assertTrue(decision.is_due)
        self.assertEqual(decision.attempts, 0)
        self.assertEqual(decision.reason, "new_item")

    def test_first_success_consolidates_regardless_of_attempt_count(self):
        decision = self.decide([attempt(1)])
        self.assertEqual(decision.state, LearningState.CONSOLIDATING)
        self.assertEqual(decision.next_due_at, START + timedelta(days=3))
        self.assertEqual(decision.independent_successes, 1)
        self.assertEqual(decision.qualified_successes, 1)

    def test_spaced_independent_success_enters_maintenance(self):
        decision = self.decide([attempt(1), attempt(2, hours=24)])
        self.assertEqual(decision.state, LearningState.MAINTENANCE)
        self.assertEqual(decision.next_due_at, START + timedelta(days=8))
        self.assertEqual(decision.maintenance_step, 0)

    def test_qualification_boundary_is_elapsed_time_not_calendar_day(self):
        before = START + timedelta(days=1) - timedelta(microseconds=1)
        early = self.decide([attempt(1), attempt(2, occurred_at=before)])
        exact = self.decide([attempt(1), attempt(2, hours=24)])
        self.assertEqual(early.state, LearningState.CONSOLIDATING)
        self.assertEqual(exact.state, LearningState.MAINTENANCE)

    def test_mass_practice_and_daily_maintenance_do_not_inflate_intervals(self):
        history = [attempt(index, hours=index) for index in range(10)]
        decision = self.decide(history)
        self.assertEqual(decision.state, LearningState.CONSOLIDATING)
        self.assertEqual(decision.qualified_successes, 1)
        history = [attempt(1), attempt(2, hours=24), attempt(3, hours=48)]
        decision = self.decide(history)
        self.assertEqual(decision.maintenance_step, 0)
        self.assertEqual(decision.qualified_successes, 2)
        self.assertEqual(decision.next_due_at, START + timedelta(days=9))

    def test_spacing_is_measured_since_latest_actual_practice(self):
        history = [
            attempt(1),
            attempt(2, hours=24),
            attempt(3, hours=7 * 24),
            attempt(4, hours=8 * 24),
        ]
        # Day 8 is seven days after promotion, but only one day after practice.
        self.assertEqual(self.decide(history).maintenance_step, 0)

    def test_maintenance_progresses_and_caps_without_retiring_items(self):
        policy = Policy()
        history = [attempt(1), attempt(2, hours=24)]
        at = START + timedelta(days=1)
        for count in range(8):
            before = self.decide(history, now=at)
            interval = policy.maintenance_seconds[before.maintenance_step]
            at += timedelta(seconds=interval)
            history.append(attempt(count + 3, occurred_at=at))
            decision = self.decide(history, now=at)
            self.assertEqual(decision.state, LearningState.MAINTENANCE)
            self.assertGreater(decision.next_due_at, at)
            self.assertLessEqual(
                (decision.next_due_at - at).total_seconds(), policy.max_interval_seconds
            )
        self.assertEqual(decision.maintenance_step, len(policy.maintenance_seconds) - 1)
        self.assertEqual(decision.reason, "maintenance_cap")

    def test_all_unsuccessful_or_assisted_outcomes_reset_evidence(self):
        for outcome in (Outcome.WITH_HINTS, Outcome.CONSULTED_SOLUTION, Outcome.NOT_SOLVED):
            with self.subTest(outcome=outcome):
                history = [
                    attempt(1),
                    attempt(2, hours=24),
                    attempt(3, hours=48, outcome=outcome, confidence=5),
                ]
                decision = self.decide(history)
                self.assertEqual(decision.state, LearningState.LEARNING)
                self.assertEqual(decision.qualified_successes, 0)
                self.assertEqual(decision.independent_successes, 2)
                self.assertEqual(decision.next_due_at, START + timedelta(days=3))

    def test_timing_goal_is_separate_from_independent_success(self):
        record = item(target_seconds=1800)
        for duration, expected in ((2400, False), (1200, True), (None, None)):
            history = [attempt(1), attempt(2, hours=24, timing=Timing(measured_seconds=duration))]
            decision = self.decide(history, record=record)
            self.assertEqual(decision.state, LearningState.MAINTENANCE)
            self.assertEqual(decision.time_goal_met, expected)
        failed = self.decide(
            [attempt(1, outcome=Outcome.NOT_SOLVED, timing=Timing(measured_seconds=60))],
            record=record,
        )
        self.assertIsNone(failed.time_goal_met)

    def test_lapse_requires_new_delayed_evidence_and_preserves_lifetime_count(self):
        history = [
            attempt(1),
            attempt(2, hours=24),
            attempt(3, hours=48, outcome=Outcome.NOT_SOLVED),
            attempt(4, hours=49),
        ]
        decision = self.decide(history)
        self.assertEqual(decision.state, LearningState.CONSOLIDATING)
        self.assertEqual(decision.independent_successes, 3)
        self.assertEqual(decision.qualified_successes, 1)
        history.append(attempt(5, hours=73))
        self.assertEqual(self.decide(history).state, LearningState.MAINTENANCE)

    def test_duplicate_retries_and_unordered_history(self):
        first, second = attempt(1), attempt(2, hours=24)
        self.assertEqual(self.decide([second, first, first]), self.decide([first, second]))
        with self.assertRaises(ValueError):
            self.decide([first, replace(first, outcome=Outcome.NOT_SOLVED)])
        with self.assertRaises(ValueError):
            self.decide([first, attempt(2)])

    def test_foreign_future_and_precreation_events_rejected(self):
        bad = [
            attempt(1, owner_id=UUID(int=50)),
            attempt(1, item_id=UUID(int=50)),
            attempt(1, hours=-1),
            attempt(1, hours=401 * 24),
        ]
        for event in bad:
            with self.subTest(event=event), self.assertRaises(ValueError):
                self.decide([event])
        with self.assertRaises(ValueError):
            self.decide(now=START - timedelta(seconds=1))

    def test_archived_preserves_evidence_but_has_no_due_date(self):
        history = [attempt(1), attempt(2, hours=24)]
        decision = self.decide(
            history,
            record=item(archived=True),
            override=self.override(requested_days=2, due_days=10),
        )
        self.assertEqual(decision.state, LearningState.ARCHIVED)
        self.assertIsNone(decision.next_due_at)
        self.assertIsNone(decision.proposed_due_at)
        self.assertEqual(decision.attempts, 2)
        self.assertEqual(decision.override_status, "ignored_archived")
        self.assertFalse(decision.is_due)

    def test_snooze_and_sooner_preserve_policy_proposal_and_evidence(self):
        history = [attempt(1)]
        for kind, due in ((OverrideKind.REVIEW_SOONER, 1), (OverrideKind.SNOOZE, 5)):
            override = self.override(requested_days=0.5, due_days=due, kind=kind)
            decision = self.decide(history, override=override)
            self.assertEqual(decision.next_due_at, START + timedelta(days=due))
            self.assertEqual(decision.proposed_due_at, START + timedelta(days=3))
            self.assertEqual(decision.qualified_successes, 1)
            self.assertEqual(decision.override_status, "applied")
            self.assertEqual(decision.applied_override_id, override.id)

    def test_stale_override_cannot_change_a_newer_attempt_schedule(self):
        decision = self.decide(
            [attempt(1), attempt(2, hours=48)], override=self.override(requested_days=1, due_days=5)
        )
        self.assertEqual(decision.override_status, "ignored_stale")
        self.assertEqual(decision.next_due_at, START + timedelta(days=9))

    def test_invalid_override_direction_bounds_and_owner(self):
        bad = [
            self.override(requested_days=0.5, due_days=5, kind=OverrideKind.REVIEW_SOONER),
            self.override(requested_days=0.5, due_days=1),
            self.override(requested_days=0.5, due_days=100),
            self.override(requested_days=0.5, due_days=5, owner_id=UUID(int=50)),
            self.override(requested_days=401, due_days=402),
        ]
        for override in bad:
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.decide([attempt(1)], override=override)

    def test_policy_config_is_validated_and_fingerprinted(self):
        self.assertEqual(Policy().fingerprint, Policy().fingerprint)
        changed = Policy(retry_seconds=2 * DAY, spaced_successes_required=3)
        self.assertNotEqual(changed.fingerprint, Policy().fingerprint)
        self.assertEqual(
            self.decide([attempt(1), attempt(2, hours=24)], policy=changed).state,
            LearningState.CONSOLIDATING,
        )
        for values in (
            {"retry_seconds": True},
            {"spaced_successes_required": 1},
            {"maintenance_seconds": (7 * DAY, 7 * DAY)},
            {"max_interval_seconds": 0},
            {"maintenance_seconds": ()},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Policy(**values)

    def test_overdue_reads_do_not_silently_snooze_and_difficulty_does_not_retire(self):
        history = [attempt(1), attempt(2, hours=24)]
        for difficulty in (Difficulty.MEDIUM, Difficulty.HARD):
            record = item(content=replace(item().content, difficulty=difficulty))
            early = self.decide(history, record=record, now=START + timedelta(days=2))
            late = self.decide(history, record=record)
            self.assertEqual(early.next_due_at, late.next_due_at)
            self.assertFalse(early.is_due)
            self.assertTrue(late.is_due)

    def test_datetime_overflow_is_explicit_but_archive_needs_no_future_date(self):
        end = datetime.max.replace(tzinfo=UTC)
        record = item(created_at=end)
        event = attempt(1, occurred_at=end)
        with self.assertRaisesRegex(ValueError, "datetime range"):
            self.decide([event], record=record, now=end)
        archived = self.decide([event], record=replace(record, archived=True), now=end)
        self.assertIsNone(archived.next_due_at)


if __name__ == "__main__":
    unittest.main()
