"""Deterministic baseline policy. Intervals are configurable pilot heuristics."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from practice.models import Attempt, LearningItem, Outcome, OverrideKind, ReviewOverride, utc

DAY = 86_400


class LearningState(StrEnum):
    LEARNING = "learning"
    CONSOLIDATING = "consolidating"
    MAINTENANCE = "maintenance"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class Policy:
    version: str = "baseline-v1"
    retry_seconds: int = DAY
    consolidation_seconds: int = 3 * DAY
    qualifying_gap_seconds: int = DAY
    spaced_successes_required: int = 2
    maintenance_seconds: tuple[int, ...] = (7 * DAY, 14 * DAY, 30 * DAY, 60 * DAY, 90 * DAY)
    min_interval_seconds: int = 3600
    max_interval_seconds: int = 90 * DAY

    def __post_init__(self):
        if not isinstance(self.version, str) or not self.version.strip() or len(self.version) > 100:
            raise ValueError("policy version must be a nonempty identifier")
        values = (
            self.retry_seconds,
            self.consolidation_seconds,
            self.qualifying_gap_seconds,
            self.min_interval_seconds,
            self.max_interval_seconds,
        )
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("policy intervals must be positive integer seconds")
        if not self.min_interval_seconds <= self.max_interval_seconds <= 3650 * DAY:
            raise ValueError("invalid interval bounds (maximum ten years)")
        if (
            type(self.spaced_successes_required) is not int
            or not 2 <= self.spaced_successes_required <= 20
        ):
            raise ValueError("maintenance requires 2..20 spaced independent successes")
        if (
            not isinstance(self.maintenance_seconds, tuple)
            or not self.maintenance_seconds
            or any(type(value) is not int for value in self.maintenance_seconds)
        ):
            raise ValueError("maintenance intervals must be a nonempty tuple of integers")
        intervals = (
            self.retry_seconds,
            self.consolidation_seconds,
            self.qualifying_gap_seconds,
            *self.maintenance_seconds,
        )
        if any(
            not self.min_interval_seconds <= value <= self.max_interval_seconds
            for value in intervals
        ):
            raise ValueError("all intervals must be within policy bounds")
        if any(a >= b for a, b in zip(self.maintenance_seconds, self.maintenance_seconds[1:])):
            raise ValueError("maintenance intervals must strictly increase")
        if self.maintenance_seconds[0] < self.qualifying_gap_seconds:
            raise ValueError("maintenance interval cannot be shorter than the qualifying gap")

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Decision:
    owner_id: UUID
    item_id: UUID
    state: LearningState
    attempts: int
    independent_successes: int
    qualified_successes: int
    maintenance_step: int | None
    proposed_due_at: datetime | None
    next_due_at: datetime | None
    reason: str
    policy_version: str
    policy_fingerprint: str
    evaluated_at: datetime
    latest_attempt_id: UUID | None
    time_goal_met: bool | None
    override_status: str
    applied_override_id: UUID | None

    @property
    def is_due(self) -> bool:
        return self.next_due_at is not None and self.next_due_at <= self.evaluated_at


def _after(timestamp: datetime, seconds: int) -> datetime:
    try:
        return timestamp + timedelta(seconds=seconds)
    except OverflowError as error:
        raise ValueError("next review exceeds the supported datetime range") from error


def _history(item: LearningItem, attempts: list[Attempt], now: datetime) -> list[Attempt]:
    events = {}
    for attempt in attempts:
        if not isinstance(attempt, Attempt):
            raise ValueError("history must contain Attempt records")
        if (attempt.owner_id, attempt.item_id) != (item.owner_id, item.id):
            raise ValueError("attempt owner/item does not match the learning item")
        if not item.created_at <= attempt.occurred_at <= now:
            raise ValueError("attempt is future-dated or predates the item")
        if attempt.id in events and events[attempt.id] != attempt:
            raise ValueError("conflicting attempt payload for the same event id")
        events[attempt.id] = attempt
    ordered = sorted(events.values(), key=lambda attempt: attempt.occurred_at)
    if any(a.occurred_at == b.occurred_at for a, b in zip(ordered, ordered[1:])):
        raise ValueError("distinct attempts need distinct timestamps for unambiguous replay")
    return ordered


def schedule(
    item: LearningItem,
    attempts: list[Attempt],
    *,
    now: datetime,
    policy: Policy | None = None,
    override: ReviewOverride | None = None,
) -> Decision:
    """Replay evidence without changing events or reading a clock/model/database.

    Exact duplicate event retries are ignored. Conflicts fail rather than silently
    choosing an outcome. This is NOT a substitute for database idempotency/ownership.
    """
    if not isinstance(item, LearningItem):
        raise ValueError("schedule requires a LearningItem")
    now = utc(now, "now")
    if now < item.created_at:
        raise ValueError("item cannot be created in the future")
    policy = Policy() if policy is None else policy
    if not isinstance(policy, Policy):
        raise ValueError("schedule requires a Policy")
    history = _history(item, attempts, now)
    if override is not None:
        if not isinstance(override, ReviewOverride):
            raise ValueError("override must be a ReviewOverride")
        if (override.owner_id, override.item_id) != (item.owner_id, item.id):
            raise ValueError("override owner/item does not match the learning item")
        if not item.created_at <= override.requested_at <= now:
            raise ValueError("override is future-dated or predates the item")

    state = LearningState.LEARNING
    qualified = independent = 0
    step = None
    previous = None
    due = item.created_at
    reason = "new_item"
    for attempt in history:
        if attempt.outcome != Outcome.INDEPENDENT:
            state, qualified, step = LearningState.LEARNING, 0, None
            interval, reason = policy.retry_seconds, "retry_after_unsuccessful_or_assisted_attempt"
        else:
            independent += 1
            gap = (attempt.occurred_at - previous.occurred_at).total_seconds() if previous else 0
            if state == LearningState.LEARNING:
                state, qualified = LearningState.CONSOLIDATING, 1
                interval, reason = policy.consolidation_seconds, "first_independent_success"
            elif state == LearningState.CONSOLIDATING:
                qualified += int(gap >= policy.qualifying_gap_seconds)
                interval, reason = policy.consolidation_seconds, "consolidating"
                if qualified >= policy.spaced_successes_required:
                    state, step = LearningState.MAINTENANCE, 0
                    interval, reason = policy.maintenance_seconds[0], "enter_maintenance"
            else:
                interval = policy.maintenance_seconds[step]
                reason = "maintenance_early_review"
                if gap >= interval:
                    qualified += 1
                    step = min(step + 1, len(policy.maintenance_seconds) - 1)
                    interval = policy.maintenance_seconds[step]
                    reason = (
                        "maintenance_cap"
                        if step == len(policy.maintenance_seconds) - 1
                        else "maintenance_progress"
                    )
        previous = attempt

    latest = history[-1] if history else None
    if latest is not None and not item.archived:
        due = _after(latest.occurred_at, interval)
    goal_met = None
    if (
        latest is not None
        and latest.outcome == Outcome.INDEPENDENT
        and item.target_seconds is not None
        and latest.timing.effective_seconds is not None
    ):
        goal_met = latest.timing.effective_seconds <= item.target_seconds

    proposed = due
    override_status, override_id = "none", None
    if item.archived:
        state, due, proposed, reason = LearningState.ARCHIVED, None, None, "archived"
        override_status = "ignored_archived" if override is not None else "none"
    elif override is not None:
        if latest is not None and override.requested_at <= latest.occurred_at:
            override_status = "ignored_stale"
        else:
            if override.due_at > _after(override.requested_at, policy.max_interval_seconds):
                raise ValueError("override exceeds the maximum review interval")
            if (
                override.kind == OverrideKind.REVIEW_SOONER
                and override.due_at > proposed
                or override.kind == OverrideKind.SNOOZE
                and override.due_at < proposed
            ):
                raise ValueError("override due time does not match its sooner/snooze direction")
            due, override_id, override_status = override.due_at, override.id, "applied"

    return Decision(
        owner_id=item.owner_id,
        item_id=item.id,
        state=state,
        attempts=len(history),
        independent_successes=independent,
        qualified_successes=qualified,
        maintenance_step=step,
        proposed_due_at=proposed,
        next_due_at=due,
        reason=reason,
        policy_version=policy.version,
        policy_fingerprint=policy.fingerprint,
        evaluated_at=now,
        latest_attempt_id=latest.id if latest else None,
        time_goal_met=goal_met,
        override_status=override_status,
        applied_override_id=override_id,
    )
