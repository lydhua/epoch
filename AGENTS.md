# Working on Epoch

## Project intent and current state

Epoch is a deployable spaced-repetition study tool whose long-term scheduler
learns personal forgetting behavior from review history. C/C++ and PyTorch are
required parts of the stack. Read `README.md` before making architectural changes.

This repository starts with documentation only. The README describes a proposed
architecture and roadmap; do not assume that its planned directories, commands,
services, or features already exist. Keep implemented behavior clearly separated
from proposals in both code and documentation.

## Architecture boundaries

- Use C++20 for the native scheduling core, CMake for builds, and pybind11 for
  Python bindings. Keep the core independent of HTTP, databases, and PyTorch.
- Use Python and PyTorch for recall modeling, feature generation, training, and
  evaluation. Initially keep inference in Python, not a second native ML runtime.
- Use FastAPI and PostgreSQL for the service and persistent data, with a
  TypeScript/React web client. These are starting choices, not existing scaffolds.
- Keep scheduling policy, model scoring, and data access separately testable.
- Introduce directories only when they contain meaningful implementation.
- Record material architectural changes and their tradeoffs in `docs/`.
- Prefer the smallest working end-to-end slice over speculative infrastructure.

## Scheduling and ML invariants

- Treat review events as immutable evidence. Derive scheduling state from them;
  do not overwrite raw ratings with transformed labels.
- Define and version the rating-to-recall mapping and every model input feature.
- Use only information available at prediction time. Split evaluation data
  chronologically and evaluate cold-start users separately.
- Keep recall probabilities in `[0, 1]` and enforce non-increasing predicted
  recall with increasing elapsed time when history is held constant.
- A shared model must work without a trained embedding for a new user or card.
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
- Use synthetic fixtures in tests. Do not log card text or sensitive user data.
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

- Prioritize text cards, decks, reviews, and due scheduling. Defer media, Anki
  compatibility, offline sync, and native apps unless explicitly requested.
- Keep inference CPU-compatible initially and run training outside request paths.
- Deployment work must include health checks, secrets management, migrations,
  backup/restore instructions, observability, and a safe model fallback/rollback.
- Do not provision paid resources, publish datasets, deploy services, or change
  repository visibility without explicit authorization.
- Keep the README accurate as milestones become implemented. Do not add a
  license or select legal terms without the project owner's approval.
