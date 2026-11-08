"""Strict simulator-v1 ingestion and explicit, prediction-time-safe features."""

import csv
import hashlib
import math
import random
import struct
from dataclasses import dataclass
from pathlib import Path

import torch

FEATURES = ("log1p_review_index", "log1p_prior_successes", "log1p_prior_failures")
FEATURE_VERSION = 1
CSV_COLUMNS = (
    "schema_version",
    "seed",
    "session_id",
    "user_id",
    "item_id",
    "review_index",
    "elapsed_days",
    "time_days",
    "prior_successes",
    "success",
    "solve_seconds",
    "oracle_half_life_days",
    "oracle_recall_probability",
)


@dataclass(frozen=True)
class Review:
    session: int
    user: int
    item: int
    index: int
    elapsed: float
    time: float
    successes: int
    success: int


@dataclass
class Dataset:
    reviews: list[Review]
    sha256: str
    simulator_seed: int


def _integer(row: dict, field: str) -> int:
    value = row[field]
    if not value or not value.isascii() or not value.isdecimal():
        raise ValueError(f"{field} must be a nonnegative integer")
    return int(value)


def _positive(row: dict, field: str) -> float:
    value = float(row[field])
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field} must be finite and positive")
    return value


def _elapsed(row: dict) -> float:
    value = _positive(row, "elapsed_days")
    narrowed = struct.unpack("f", struct.pack("f", value))[0]
    if not math.isfinite(narrowed) or narrowed <= 0:
        raise ValueError("elapsed_days must remain finite and positive in float32")
    return value


def load_reviews(path: Path, max_rows: int = 200_000) -> Dataset:
    """Hash the bytes parsed; reject incomplete rows, reordering, or mixed histories.

    This first loader is deliberately bounded/in-memory. Large-scale out-of-core
    ingestion is separate work, not implied by the C++ generator's scale target.
    """
    if max_rows < 1:
        raise ValueError("max_rows must be positive")
    digest = hashlib.sha256()
    reviews = []
    previous = None
    seed = None
    with path.open("rb") as source:

        def lines():
            for line in source:
                digest.update(line)
                yield line.decode("utf-8")

        reader = csv.DictReader(lines())
        if tuple(reader.fieldnames or ()) != CSV_COLUMNS:
            raise ValueError("expected exact simulator-v1 CSV header")
        for line_number, row in enumerate(reader, 2):
            try:
                if len(reviews) >= max_rows:
                    raise ValueError("dataset exceeds max_rows; use a smaller initial experiment")
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("incomplete or extra CSV fields")
                if _integer(row, "schema_version") != 1:
                    raise ValueError("unsupported CSV schema version")
                current_seed = _integer(row, "seed")
                if seed is not None and current_seed != seed:
                    raise ValueError("mixed simulator seeds")
                seed = current_seed
                review = Review(
                    session=_integer(row, "session_id"),
                    user=_integer(row, "user_id"),
                    item=_integer(row, "item_id"),
                    index=_integer(row, "review_index"),
                    elapsed=_elapsed(row),
                    time=_positive(row, "time_days"),
                    successes=_integer(row, "prior_successes"),
                    success=_integer(row, "success"),
                )
                if review.success not in (0, 1):
                    raise ValueError("success must be binary")
                # Diagnostics are checked but NEVER used by the feature builder.
                _positive(row, "solve_seconds")
                _positive(row, "oracle_half_life_days")
                oracle = float(row["oracle_recall_probability"])
                if not math.isfinite(oracle) or not 0 <= oracle <= 1:
                    raise ValueError("invalid diagnostic recall probability")
                same_session = previous is not None and review.session == previous.session
                if same_session:
                    if (review.user, review.item) != (previous.user, previous.item):
                        raise ValueError("user/item changed within session")
                    expected_index = previous.index + 1
                    expected_successes = previous.successes + previous.success
                    expected_time = previous.time + review.elapsed
                else:
                    if previous is not None and review.session <= previous.session:
                        raise ValueError("sessions must be strictly increasing and grouped")
                    expected_index, expected_successes, expected_time = 0, 0, review.elapsed
                if review.index != expected_index or review.successes != expected_successes:
                    raise ValueError("inconsistent review index or pre-attempt success count")
                if not math.isclose(review.time, expected_time, rel_tol=1e-9, abs_tol=1e-9):
                    raise ValueError("inconsistent session-relative time")
                if max(review.index, review.successes) > 100 or review.elapsed > 1_000_000:
                    raise ValueError("review outside supported experiment bounds")
                reviews.append(review)
                previous = review
            except (ValueError, TypeError, OverflowError) as error:
                raise ValueError(f"CSV line {line_number}: {error}") from error
    if not reviews:
        raise ValueError("dataset has no reviews")
    return Dataset(reviews, digest.hexdigest(), seed)


def split_reviews(reviews: list[Review], seed: int) -> dict[str, list[Review]]:
    """Hold out whole users; split remaining session histories 60/20/20 by time."""
    users = sorted({review.user for review in reviews})
    if len(users) < 3:
        raise ValueError("need at least three users for warm/cold evaluation")
    random.Random(seed).shuffle(users)
    cold_users = set(users[: max(1, len(users) // 5)])
    sessions = {}
    for review in reviews:
        sessions.setdefault(review.session, []).append(review)
    splits = {name: [] for name in ("train", "validation", "warm_test", "cold_test")}
    for history in sessions.values():
        if len(history) < 5:
            raise ValueError("every session needs at least five reviews")
        if history[0].user in cold_users:
            splits["cold_test"].extend(history)
            continue
        train_end = int(0.6 * len(history))
        validation_end = min(len(history) - 1, max(train_end + 1, int(0.8 * len(history))))
        splits["train"].extend(history[:train_end])
        splits["validation"].extend(history[train_end:validation_end])
        splits["warm_test"].extend(history[validation_end:])
    return splits


def user_vocabulary(reviews: list[Review]) -> dict[int, int]:
    return {user: index + 1 for index, user in enumerate(sorted({r.user for r in reviews}))}


def tensors(reviews: list[Review], users: dict[int, int]) -> dict[str, torch.Tensor]:
    # IDs and elapsed time do not enter the history network. Elapsed time enters
    # only through the decay equation, preserving monotonicity by construction.
    elapsed = torch.tensor([r.elapsed for r in reviews], dtype=torch.float32)
    if not torch.isfinite(elapsed).all() or not (elapsed > 0).all():
        raise ValueError("elapsed_days must remain finite and positive in float32")
    return {
        "history": torch.tensor(
            [
                [math.log1p(r.index), math.log1p(r.successes), math.log1p(r.index - r.successes)]
                for r in reviews
            ],
            dtype=torch.float32,
        ),
        "elapsed": elapsed,
        "user": torch.tensor([users.get(r.user, 0) for r in reviews], dtype=torch.long),
        "target": torch.tensor([r.success for r in reviews], dtype=torch.float32),
    }
