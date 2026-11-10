# Practice v1: domain contracts and baseline policy

Implemented as a Python 3.12 standard-library-only module in `practice/`. This is
a testable foundation used by the [API adapter](api-v1.md), not a deployed
application or validated learning policy. It is independent of the experimental ML model.

## Records

- **Collection:** UUID, owner UUID, name.
- **LearningItem:** UUID, owner/collection UUIDs, title, UTC creation time, tags,
  optional time goal in seconds, explicit archive flag, and typed content.
  Coding problems hold an HTTPS URL and optional difficulty; flashcards hold
  front/back text; other exercises hold instructions. The activity type is derived
  from content, not a second field that could disagree. No card fields are required
  for coding practice.
- **Attempt:** UUID/idempotency identity, owner/item UUIDs, UTC occurrence time,
  outcome, optional timing evidence, and optional confidence (1..5). Outcomes are
  independent, with hints, consulted solution, and not solved. These are explicit
  observations, not auto-converted ML labels.
- **Timing:** optional measured active seconds, optional corrected/manual seconds,
  and optional correction reason. The original measurement is retained. Zero is
  distinct from missing; a correction to zero must not fall back to measured time.
  Effective duration prefers the corrected value. This stores timing evidence; it
  does not implement the frontend's timer or verify whether pauses were recorded.
- **ReviewOverride:** UUID, owner/item, requested time, requested due time, and
  `review_sooner` or `snooze`. Overrides never become successful attempts.
- **Decision:** state, counters, maintenance step, policy-proposed and final due
  dates, explanation, policy version/configuration hash, evaluation time, latest
  attempt identity, latest independent attempt's time-goal result, and override
  application status.

All records are frozen dataclasses with validated UUIDs/enums, bounded text, and
finite numeric evidence. Incoming timestamps must have an explicit timezone and
are normalized to UTC. Tags are copied into an immutable tuple. Boundary adapters
parse JSON strings into UUIDs, datetimes, and enums. Text rejects NUL characters
and unpaired Unicode surrogates so valid records can be stored in PostgreSQL.
HTTPS URL validation does not authorize server-side fetching: this module performs
no network requests and does not establish an SSRF protection policy.

## Baseline v1 defaults

These are configurable, conservative pilot choices, **not optimal intervals or
research-proven mastery criteria**:

| Setting | Initial value |
| --- | --- |
| Retry after unsuccessful/assisted attempt | 1 day |
| Consolidation review | 3 days |
| Minimum qualifying gap | 24 hours |
| Independent spaced successes before maintenance | 2 |
| Maintenance intervals | 7, 14, 30, 60, 90 days |
| Policy interval bounds | 1 hour to 90 days |

All durations use explicit seconds internally. A new item is due at creation.
The first independent success enters **consolidating**. Further independent
successes qualify toward maintenance only after the configured gap since the
**latest actual attempt**, not since an older milestone or a calendar-day change.
Early independent repeats retain the state and do not inflate the qualified count.

After the configured spaced-success count, the item enters **maintenance** at
the first maintenance interval. Thereafter an independent success advances one
step only if the full current interval has passed since the latest attempt.
An early repeat restarts the current interval without increasing it. A late
review advances at most one step, rather than jumping to an extreme interval.
The last step repeats indefinitely: no active item is automatically retired,
including medium/hard coding problems.

Hints, solution consultation, or an unsuccessful attempt reset qualified evidence
and return the item to **learning** with a retry date. Lifetime attempt and
independent-success totals remain intact. An explicit archive flag instead removes
the due date while preserving historical evidence; reactivating replays the history.

Next due dates are anchored to the latest actual attempt, not to the time a page
is opened. Reading an overdue item never silently snoozes it. Archived records
need no future timestamp. If a required active due date cannot fit in Python's
datetime range, scheduling raises a clear error rather than overflowing.

Difficulty does not automatically change forgetting rate. Time goals are set per
item, not through a universal interview cutoff. Slow independent success remains
success; missing time is unknown, not failure or zero. `time_goal_met` is null
unless the latest attempt was independent and both duration and goal exist.
Confidence is preserved but does not alter this policy. Modeling time-to-solve,
using confidence predictively, and daily-budget prioritization are future work.

## Replay and overrides

`schedule(item, attempts, now=..., policy=..., override=...)` is a pure function:
it does not mutate inputs, read a clock, query storage, or call an ML model.

- Attempts must match the item's owner/identity and fall between creation and the
  injected evaluation time. Out-of-order input is sorted by occurrence time.
- Exact duplicate events are deduplicated. The same UUID with a different payload
  is an error, not an update. Different UUIDs with identical occurrence timestamps
  are rejected as ambiguous until a persistent event-sequence contract is added.
- The original policy proposal remains available when applying an override. A
  sooner request cannot move it later; a snooze cannot move it earlier. Due time
  cannot precede the request or exceed the configured maximum interval from it.
- Overrides at or before the latest attempt are stale and ignored explicitly;
  an archived item ignores overrides. Owner/identity and request-time validation
  still applies. Only one caller-selected override is accepted; persistence will
  determine the latest applicable request and retain the full override history.
- Immediate review is permitted through a fresh sooner override. For an item
  already overdue, it is already eligible; no sooner override is necessary.

An applied override changes neither the success counts nor the policy proposal.
When another attempt is recorded, the old override becomes stale. Expired due
dates remain due; opening the queue does not renew them.

## Example

```python
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from practice.models import Attempt, CodingProblem, LearningItem, Outcome
from practice.scheduler import schedule

owner, collection = uuid4(), uuid4()
start = datetime(2026, 1, 1, tzinfo=UTC)
problem = LearningItem(
    id=uuid4(), owner_id=owner, collection_id=collection, title="Two Sum",
    content=CodingProblem("https://leetcode.com/problems/two-sum/"), created_at=start,
)
attempts = [
    Attempt(uuid4(), owner, problem.id, start, Outcome.INDEPENDENT),
    Attempt(uuid4(), owner, problem.id, start + timedelta(days=1), Outcome.INDEPENDENT),
]
decision = schedule(problem, attempts, now=start + timedelta(days=1))
assert decision.state == "maintenance"
assert decision.next_due_at == start + timedelta(days=8)
```

Run the suite in the locked environment:

```sh
uv run --frozen python -m unittest discover -s practice/tests -v
uv run --frozen ruff check practice
uv run --frozen ruff format --check practice
```

The suite also runs on Python 3.12 with `-S` (without site packages), exercising
UTC validation, timing provenance, replay/conflicts, ownership checks, spacing,
maintenance/lapses, bounded overrides, and date overflow. CI has a separate
domain-test job.

## Next integration boundary

The first [FastAPI/PostgreSQL adapter](api-v1.md) and migration now wrap these contracts.
Derive the
owner from authentication, not from a trusted request-body UUID. Enforce ownership
in every query and collection link, and persist each attempt plus its scheduling
decision transactionally. Database uniqueness and idempotency must handle races
across processes; in-memory replay does not provide that guarantee. Preserve
submitted events and use separate correction events for post-submission edits.

Save the decision's policy version and exact configuration fingerprint alongside
its proposal, applied override, and explanation. A model-assisted policy can later
share the same decision boundary and use this policy as fallback; no model is
enabled for live scheduling here. The adapter has token verification, persistence,
and basic endpoints; full account lifecycle, due-queue UI, timer controls,
deployment, and real-world effectiveness remain unimplemented.
