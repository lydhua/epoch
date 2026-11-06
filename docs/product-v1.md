# Product v1: coding practice on a general learning model

These are requirements, not implemented features. Favor a usable vertical slice,
readable boundaries, meaningful tests, measured performance, and reproducible
deployment over extra services.

## Learning records

Collections contain learning items; items have an activity type and typed
metadata. Coding items have a problem URL, difficulty, and tags. Attempts are
append-only events with outcomes, time evidence, and scheduling provenance.
Flashcards remain an optional type rather than the base schema for every item.

For coding practice, capture independently solved, solved with hints, consulted
solution, or not solved. Capture self-assessed confidence separately; absence of
a rating is not failure. Timing is optional: missing time must not mean zero or
automatically worsen the success label. Previous attempt times may inform future
predictions, but current solve time is only known after the attempt.

## Optional timer

- A user gesture on **Start** opens the stored problem URL in a new tab and starts
  Epoch's timer. Validate HTTPS problem URLs, isolate the opener, and report popup
  blocking with a manual link fallback; do not silently claim the tab opened.
- Support pause, resume, reset/start over, and manual duration entry/correction.
  Confirm destructive resets and prevent duplicate active timers for one attempt.
- Paused time is excluded. Store accumulated active time and the latest running
  start timestamp; do not count `setInterval` ticks as elapsed time. Handle refresh,
  tab suspension, clock anomalies, and multi-tab conflicts explicitly.
- Show the recorded duration before submission. Preserve measured duration,
  user-corrected duration, and provenance separately; corrections must not erase
  the original evidence. Saving an attempt must be idempotent.
- Do not depend on reading LeetCode's internal timer. Cross-origin browser rules
  prevent ordinary page access, and no supported integration has been established.
  No scraping, browser extension, or account access is assumed.

Acceptance tests should cover start/open, blocked popup, pause/resume, correction,
reset, reload recovery, missing timing, duplicate submissions, and keyboard access.

## Learning and maintenance

Keep exposure count, independent success count, solve time, and confidence as
separate evidence. The user's spreadsheet rule was at least three total attempts
plus independent solving, not three independent successes. It was a convenient
heuristic, not a requirement for Epoch. Replace it with an evaluated policy rather
than hard-coding it as mastery. See [the research note](research/mastery-and-spacing.md)
for evidence, limitations, and a proposed pilot approach; numeric thresholds remain
experimental, not established scientific defaults.

Track **learning**, **maintenance**, and **archived** separately. "Learned" enters
maintenance: it never means "never review again." Successful maintenance reviews
can earn long intervals; failures or requested earlier reviews bring them forward.
Keep every active item eligible for a bounded future review, including mediums
and hards. Interval caps and difficulty-specific policy require evaluation, not
arbitrary hard-coded claims about retention.

Allow explicit "review sooner" and "snooze" preferences, recording the override
separately from model predictions and success labels. Confidence can inform policy
with bounded influence; it must not erase observed failures. Solve-time goals
should be configurable by difficulty/user rather than one universal interview
cutoff. Track independent success and time-to-solve separately before combining
them into an interview-readiness objective. A 90% retention target is exploratory,
not an established default for long coding problems.

## Delivery quality

- CI: compiler/build matrix, warnings as errors, unit tests, CLI/schema integration
  tests, and sanitizer checks; later add Python, API, and frontend test suites.
- Product tests: authorization/ownership, idempotency, maintenance scheduling,
  timer transitions, and full attempt-to-next-due flows.
- CD: automated staging deployment and smoke tests once there is a service,
  explicit production approval, secret isolation, migrations, and rollback.
- Project documentation: architecture decisions, reproducible benchmarks and model
  metrics, a working demo, and honest documentation of limitations. Never claim
  configured workflows have passed until they actually run.
