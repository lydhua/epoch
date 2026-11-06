# Working on Epoch

## Project intent and current state

Epoch is a deployable spaced-repetition study tool whose long-term scheduler
learns personal forgetting behavior from review history. C/C++ and PyTorch are
required parts of the stack. Read `README.md` before making architectural changes.

Support general learning activities, not just flashcards. The initial product
use case is LeetCode-style problem practice; flashcards are an optional activity
type. Model collections, learning items, and attempts independently of front/back
card fields. Broad applicability is a design goal, not proof that one outcome
definition or trained model works equally well for every kind of learning.

This repository has a C++ simulator, tests, and CI configuration. The model,
application, frontend, and deployment are still planned. Do not assume planned
directories or services exist. Keep implemented behavior clearly separated from
proposals in both code and documentation.

SWE recruiting is an explicit goal. Favor readable design, meaningful automated
tests, reproducible measurements, and a usable deployed slice over extra services.
Read `docs/experiment-v1.md` and `docs/product-v1.md` for the current contracts.

## Architecture boundaries

- Use C++20 and CMake for simulation. Start scheduling in Python; defer a native
  scheduling core and pybind11 until a measured need justifies the boundary.
- Use Python and PyTorch for recall modeling, feature generation, training, and
  evaluation. Initially keep inference in Python, not a second native ML runtime.
- Include a C++ simulation pipeline targeting 500,000 synthetic learning sessions
  with individualized forgetting curves, feeding a future PyTorch recall model.
  The generator exists; training is not implemented yet. Keep generation
  configurable and reproducible; distinguish sessions from individual review events.
- Use FastAPI and PostgreSQL for the service and persistent data, with a
  TypeScript/React web client. These are starting choices, not existing scaffolds.
- Keep scheduling policy, model scoring, and data access separately testable.
- Preserve optional measured and corrected timing separately, including pause/
  resume semantics. Do not depend on accessing LeetCode's timer. Learned items
  remain eligible for maintenance reviews; user overrides are not success labels.
- Introduce directories only when they contain meaningful implementation.
- Record material architectural changes and their tradeoffs in `docs/`.
- Prefer the smallest working end-to-end slice over speculative infrastructure.

## Scheduling and ML invariants

- Treat review events as immutable evidence. Derive scheduling state from them;
  do not overwrite raw ratings with transformed labels.
- Define and version the rating-to-recall mapping and every model input feature.
- Preserve activity-specific outcomes, including independent solutions, hints,
  solution consultation, and failures for coding problems. Do not equate task
  completion, approach recall, and flashcard recall without an explicit mapping.
- Evaluate models by activity type and distinguish synthetic-data performance
  from real-world validity. Keep generated datasets out of version control.
- Use only information available at prediction time. Split evaluation data
  chronologically and evaluate cold-start users separately.
- Keep recall probabilities in `[0, 1]` and enforce non-increasing predicted
  recall with increasing elapsed time when history is held constant.
- A shared model must work without a trained embedding for a new user or item.
- Keep a deterministic, documented bootstrap/fallback scheduler. Test missing
  artifacts, invalid predictions, insufficient history, and inference failures.
- Bound intervals and handle failed, overdue, repeated, and out-of-order reviews
  explicitly. Persist scheduler/model versions and fallback reasons.
- Inject clocks and random seeds where needed for reproducible tests.
- Version model artifacts, feature schemas, and dataset lineage together. Validate
  artifact/schema compatibility before activation and preserve rollback support.
- Never claim personalization or improved retention based only on synthetic
  data, training loss, or offline prediction metrics.

## Data and security

- Store timestamps in UTC and use explicit units for elapsed times and intervals.
- Make review submission idempotent and scheduling-state updates transactional.
- Enforce ownership on every user-scoped query; test cross-user access denial.
- Do not commit credentials, `.env` files, real user histories, database dumps,
  generated datasets, or large model checkpoints. Add appropriate ignore rules
  when creating the first implementation artifacts.
- Use synthetic fixtures in tests. Do not log learning content, submitted code,
  or sensitive user data.
- Treat cross-user training as a privacy decision requiring explicit consent
  and documented retention/deletion behavior, not an automatic default.
- Never load untrusted pickle-based models or run untrusted model artifacts.

## Engineering and validation

- Follow surrounding conventions; add formatters and dependency manifests when
  introducing each language. Pin reproducible environments with suitable lockfiles.
- Use RAII and explicit ownership in C++; avoid raw owning pointers. Validate
  boundary inputs and translate native errors into useful Python exceptions.
- Add C++ tests for interval selection, bounds, deterministic behavior, and edge
  cases; run native tests with sanitizers in supported development/CI environments.
- Add Python tests for feature/label correctness, temporal leakage, model output
  properties, cold start, artifact loading, and fallback behavior.
- Test the Python/native boundary and complete review-to-next-due flow. Test API
  authorization, duplicate submissions, transactions, and migration behavior.
- Add web tests for the study workflow and accessible keyboard interaction.
- Keep expensive model training separate from ordinary unit tests; use small
  deterministic models and synthetic fixtures for routine checks.
- Do not invent working commands. Once a component exists, document its actual
  install, build, test, and run commands in the README and configure CI to use them.
- Run relevant available checks after changes. Report what ran and what could
  not run; never describe an unexecuted check as passing.

## Scope and deployment

- Prioritize linked coding problems, collections, manual attempt recording, and
  due scheduling on a generic learning-item model. Flashcards can be added as an
  activity type, not as a constraint on every item. Defer automated code execution,
  third-party account integration, Anki compatibility, offline sync, and native
  apps unless explicitly requested.
- Keep inference CPU-compatible initially and run training outside request paths.
- Deployment work must include health checks, secrets management, migrations,
  backup/restore instructions, observability, and a safe model fallback/rollback.
- Do not provision paid resources, publish datasets, deploy services, or change
  repository visibility without explicit authorization.
- Never push to any remote repository without the user's explicit permission
  for that push. Permission to edit files or create local commits is not permission
  to push; previous push authorization does not authorize future pushes. If unsure,
  ask before running `git push` or any command that implicitly pushes changes.
- Keep the README accurate as milestones become implemented. Do not add a
  license or select legal terms without the project owner's approval.
