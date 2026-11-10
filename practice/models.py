"""Immutable, activity-neutral learning records with explicit timing evidence."""

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import urlsplit
from uuid import UUID


def utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    try:
        return value.astimezone(UTC)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"{name} is outside the supported UTC range") from error


def identifier(value: UUID, name: str):
    if not isinstance(value, UUID):
        raise ValueError(f"{name} must be a UUID")


def text(value: str, name: str, limit: int):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must contain 1..{limit} characters")
    if "\x00" in value:
        raise ValueError(f"{name} cannot contain NUL characters")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"{name} must contain valid Unicode") from error


def seconds(value: float, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number of seconds")
    try:
        converted = float(value)
    except OverflowError as error:
        raise ValueError(f"{name} is too large") from error
    if not math.isfinite(converted) or converted < 0 or (positive and converted == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return converted


class ActivityType(StrEnum):
    CODING_PROBLEM = "coding_problem"
    FLASHCARD = "flashcard"
    EXERCISE = "exercise"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Outcome(StrEnum):
    INDEPENDENT = "independent"
    WITH_HINTS = "with_hints"
    CONSULTED_SOLUTION = "consulted_solution"
    NOT_SOLVED = "not_solved"


@dataclass(frozen=True)
class CodingProblem:
    url: str
    difficulty: Difficulty | None = None

    def __post_init__(self):
        text(self.url, "problem URL", 2048)
        if any(character.isspace() or ord(character) < 32 for character in self.url):
            raise ValueError("problem URL cannot contain whitespace or controls")
        try:
            parsed = urlsplit(self.url)
            port = parsed.port
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or port == 0
            ):
                raise ValueError("problem URL must be HTTPS without embedded credentials")
        except ValueError as error:
            raise ValueError("invalid HTTPS problem URL") from error
        if self.difficulty is not None and not isinstance(self.difficulty, Difficulty):
            raise ValueError("difficulty must be a Difficulty value")


@dataclass(frozen=True)
class Flashcard:
    front: str
    back: str

    def __post_init__(self):
        text(self.front, "front", 20_000)
        text(self.back, "back", 20_000)


@dataclass(frozen=True)
class Exercise:
    instructions: str

    def __post_init__(self):
        text(self.instructions, "instructions", 20_000)


@dataclass(frozen=True)
class Collection:
    id: UUID
    owner_id: UUID
    name: str

    def __post_init__(self):
        identifier(self.id, "collection id")
        identifier(self.owner_id, "owner id")
        text(self.name, "collection name", 200)


@dataclass(frozen=True)
class LearningItem:
    id: UUID
    owner_id: UUID
    collection_id: UUID
    title: str
    content: CodingProblem | Flashcard | Exercise
    created_at: datetime
    target_seconds: float | None = None
    tags: tuple[str, ...] = ()
    archived: bool = False

    def __post_init__(self):
        for name in ("id", "owner_id", "collection_id"):
            identifier(getattr(self, name), name)
        text(self.title, "item title", 300)
        if not isinstance(self.content, (CodingProblem, Flashcard, Exercise)):
            raise ValueError("unsupported learning content")
        object.__setattr__(self, "created_at", utc(self.created_at, "created_at"))
        if self.target_seconds is not None:
            object.__setattr__(
                self,
                "target_seconds",
                seconds(self.target_seconds, "target_seconds", positive=True),
            )
        if not isinstance(self.tags, (tuple, list)) or len(self.tags) > 50:
            raise ValueError("tags must be a list/tuple of at most 50 strings")
        for tag in self.tags:
            text(tag, "tag", 100)
        object.__setattr__(self, "tags", tuple(self.tags))
        if type(self.archived) is not bool:
            raise ValueError("archived must be boolean")

    @property
    def activity_type(self) -> ActivityType:
        if isinstance(self.content, CodingProblem):
            return ActivityType.CODING_PROBLEM
        if isinstance(self.content, Flashcard):
            return ActivityType.FLASHCARD
        return ActivityType.EXERCISE


def validate_membership(collection: Collection, item: LearningItem):
    if collection.owner_id != item.owner_id or collection.id != item.collection_id:
        raise ValueError("item must belong to its owner's collection")


@dataclass(frozen=True)
class Timing:
    measured_seconds: float | None = None
    corrected_seconds: float | None = None
    correction_reason: str | None = None

    def __post_init__(self):
        for name in ("measured_seconds", "corrected_seconds"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, seconds(value, name))
        if self.correction_reason is not None:
            if self.corrected_seconds is None:
                raise ValueError("correction reason requires a corrected/manual duration")
            text(self.correction_reason, "correction reason", 500)

    @property
    def effective_seconds(self) -> float | None:
        return (
            self.corrected_seconds if self.corrected_seconds is not None else self.measured_seconds
        )

    @property
    def source(self) -> str:
        if self.corrected_seconds is not None:
            return "corrected" if self.measured_seconds is not None else "manual"
        return "measured" if self.measured_seconds is not None else "missing"


@dataclass(frozen=True)
class Attempt:
    id: UUID
    owner_id: UUID
    item_id: UUID
    occurred_at: datetime
    outcome: Outcome
    timing: Timing = field(default_factory=Timing)
    confidence: int | None = None

    def __post_init__(self):
        for name in ("id", "owner_id", "item_id"):
            identifier(getattr(self, name), name)
        object.__setattr__(self, "occurred_at", utc(self.occurred_at, "occurred_at"))
        if not isinstance(self.outcome, Outcome) or not isinstance(self.timing, Timing):
            raise ValueError("attempt requires an Outcome and Timing record")
        if self.confidence is not None and (
            type(self.confidence) is not int or not 1 <= self.confidence <= 5
        ):
            raise ValueError("confidence must be 1..5 or missing")


class OverrideKind(StrEnum):
    REVIEW_SOONER = "review_sooner"
    SNOOZE = "snooze"


@dataclass(frozen=True)
class ReviewOverride:
    id: UUID
    owner_id: UUID
    item_id: UUID
    requested_at: datetime
    due_at: datetime
    kind: OverrideKind

    def __post_init__(self):
        for name in ("id", "owner_id", "item_id"):
            identifier(getattr(self, name), name)
        object.__setattr__(self, "requested_at", utc(self.requested_at, "requested_at"))
        object.__setattr__(self, "due_at", utc(self.due_at, "due_at"))
        if not isinstance(self.kind, OverrideKind):
            raise ValueError("override requires an OverrideKind")
        if self.due_at < self.requested_at:
            raise ValueError("override due time cannot precede its request")
