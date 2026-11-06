# Experiment v1: simulator to recall prediction

## Scope and definitions

This experiment tests whether a small PyTorch model can predict synthetic review
outcomes and benefit from learner history. It does not measure interview readiness
or establish that the scheduling policy improves real learning.

- **Attempt/review:** one observation of a learner revisiting one item.
- **Synthetic session:** one learner-item trajectory containing multiple reviews.
  This is a dataset grouping, not the product's timer session or a calendar day.
- **Scale target:** 500,000 sessions, eight reviews each: 4,000,000 event rows.
- **Initial exposure:** occurs at relative day zero, before exported reviews.
- **Synthetic success:** a Bernoulli draw from a simulated forgetting curve.
- **Product success target:** independently solving a previously studied problem;
  not yet implemented and not validated by the synthetic label.

## Generator v1 (implemented)

User half-lives are log-uniform between 1 and 14 days, configurable through the
C++ library. Sessions are assigned round-robin to users. Each has a distinct item
with difficulty uniform in `[0.7, 1.5)`. Initial half-life is the user's half-life
divided by item difficulty. User effects persist across sessions; this version
does not model shared items across users or topic transfer.

At each review, elapsed time is sampled log-uniformly between 0.25 and 30 days,
independently of hidden learner parameters. Success probability is
`2 ** (-elapsed_days / half_life_days)`. After the observation, half-life increases
by 1.35 on success and 1.1 on failure, assuming solution study after every attempt.
These are deliberately inspectable simulation assumptions, not cognitive laws.

Synthetic attempt duration is uniform between 300 and 2400 seconds, multiplied
by item difficulty and by 1.5 on failure. It is a placeholder correlated with
outcome, not a realistic interview-time model. Do not use it to justify a timing
policy; future simulators should vary speed and forgetting independently.

The seed, schema version, grouping IDs, and pre-attempt history are in the CSV.
Record the generator commit, complete CLI arguments, compiler/platform, and file
SHA-256 alongside an experimental dataset. Repeated runs are byte-reproducible
on the same toolchain; floating-point math may differ across platforms.
Generation streams rows, using memory proportional to user count rather than
event count. On macOS/Linux, it writes inside a private sibling staging directory
created exclusively by `mkdtemp`, closes and checks the file, then publishes it
using atomic no-replace hard-link creation. Existing entries (including dangling
symlinks) are rejected. Concurrent writers cannot replace the winner's output.
The destination filesystem must support hard links; there is no unsafe copy or
overwrite fallback. Ordinary failures clean up staging without exposing a partial
file at the final path. Forced termination can leave a hidden `.epoch-simulate-*`
staging directory, ignored by Git, but cannot publish a partial final file. This
is atomic visibility, not a promise of power-loss durability (no `fsync`).

## Training and evaluation contract (next)

- Target: current row's `success`.
- Allowlisted initial features: `elapsed_days`, `review_index`, `prior_successes`,
  and lagged observations from the same session. User identifiers may index
  regularized effects with an explicit unseen-user fallback.
- Never use current `solve_seconds`, current outcome, `oracle_*` columns,
  future rows, or session/item IDs as numeric prediction features.
- The `oracle_*` columns exist solely for diagnostic comparisons. Persist an
  explicit feature allowlist in training code instead of dropping a few columns.
- Use chronological per-session holdouts for warm-start evaluation; separately
  hold out whole users and all their sessions for cold-start evaluation.
- Fit transforms and tune hyperparameters on training/validation data only.
- Compare against a constant probability and a fitted shared forgetting curve;
  report log loss, Brier score, calibration bins, and history-length slices.
- Start with a small time-decay PyTorch model, not a large sequence architecture.
- Evaluate shifted half-life ranges and, in a later generator version, different
  decay/learning assumptions. Fitting the same simulator family is insufficient.
- Record runtime, event count, seeds, environment, and failure cases. Synthetic
  gains must be labeled synthetic in documentation and recruiting materials.

## Engineering milestones

Current slice: dependency-free C++ library/CLI, tests, and CI configuration.
Next: reproducible PyTorch training/evaluation, then a persistent API and thin web
client. A C++ scheduler/pybind11 layer is deferred until a demonstrated need.
CI must test each introduced component. CD follows a deployable service: build an
immutable image, test it, deploy to staging, smoke-test, require approval for
production, and document rollback. No fake deploy job or unverified green badge.
