# Epoch

A spaced-repetition study tool that learns how you forget.

Epoch aims to offer an Anki-like review workflow with a scheduler informed by a
PyTorch model of recall. Rather than assigning everyone the same forgetting
curve, it will learn from each learner's review history and adapt as more evidence
becomes available.

**Status:** planning stage. This repository currently contains project and
contributor documentation only. No application, trained model, or deployment is
available yet. The architecture below is a proposed starting point, not a claim
about implemented functionality.

## Goals

- Create decks and basic front/back flashcards, then study cards when due.
- Predict recall probability from elapsed time and previous review outcomes.
- Learn a user's forgetting behavior while accounting for differences between cards.
- Choose review intervals around a configurable target retention rate.
- Compare the learned scheduler with a transparent baseline before claiming gains.
- Deploy a usable web application with portable, reproducible infrastructure.

The first release will focus on text cards and one primary workflow: create,
review, record the outcome, and schedule the next review. Anki import/export,
media cards, offline synchronization, and native mobile clients are later options.
Compatibility with Anki's scheduling algorithm or collection format is not implied.

## Proposed stack

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Scheduling core | C++20, CMake, pybind11 | Interval search, scheduling constraints, and deterministic queue logic |
| Learning | Python, PyTorch | Recall prediction, training, calibration, and model evaluation |
| API | Python, FastAPI | Authentication, decks, cards, review ingestion, and scheduling orchestration |
| Database | PostgreSQL | User-owned content, append-only review events, and scheduling state |
| Web client | TypeScript, React, Vite | Deck management and the daily study interface |
| Packaging and deployment | Docker, Docker Compose | Reproducible local services and a path to hosted deployment |

The C++ component is a real scheduling library, not a placeholder to satisfy a
language requirement. Python exposes it through pybind11. Initially, PyTorch
inference stays in Python: the API obtains a batch of candidate intervals from
the core, scores them with the model, and uses the core to select a constrained
interval. A native inference runtime can be evaluated later if profiling justifies it.

```text
React web client
       |
   FastAPI ---------------- PostgreSQL
       |
 Scheduling service
       |                 |
 C++ core (pybind11)   PyTorch recall model
                         ^
                         |
                Offline training worker
```

## Learning and scheduling design

### Record the evidence

Each review should record a unique event ID, user and card identifiers, UTC
timestamp, elapsed time since the previous review, outcome, response duration,
and the scheduler/model version that proposed the review. Preserve the learner's
original rating separately from any derived recall label. A rating-to-label
mapping must be explicit and versioned; self-reported difficulty is an imperfect
proxy for recall, not objective ground truth.

### Predict recall

Start with a small PyTorch model that predicts
`P(recall | elapsed time, review history, user, card)`.
Use a time-dependent decay parameterization with non-increasing recall probability
as elapsed time increases, rather than unconstrained interval predictions.
Candidate features include prior successes and failures, previous intervals,
review count, and learned user/card effects. Do not require card text for the
first model.

Use a shared population model with regularized user-level adaptation so that
personalization does not depend on training an independent model for every user.
New users and cards back off to shared parameters. Before a validated model and
sufficient data exist, use a documented deterministic bootstrap scheduler. This
fallback is necessary for cold start; it is not the intended long-term source of
personalized intervals.

### Choose a review time

Given a target retention probability (initially proposed as 90%), select the
longest supported interval whose predicted recall remains above the target.
Enforce minimum/maximum intervals and sensible handling of failed or overdue
reviews. Fall back safely when the model is unavailable, produces invalid output,
or lacks sufficient evidence. Store the reason for each scheduling decision.

### Validate before rollout

- Establish a deterministic baseline and test learned scheduling against it.
- Use chronological splits and history available only at prediction time; never
  leak future reviews into features. Also evaluate held-out users for cold start.
- Track log loss, Brier score, calibration, and performance by history length.
- Evaluate retention alongside review workload; predictive accuracy alone does
  not establish that a scheduling policy improves learning.
- Version datasets, feature definitions, model artifacts, and evaluation results.
- Use synthetic data to test the pipeline, not as evidence of real learning gains.
- Begin with shadow predictions, then consider an opt-in controlled comparison.

## Planned repository layout

These directories will be introduced as their components are implemented:

```text
core/           C++ scheduling library, bindings, and unit tests
ml/             PyTorch models, features, training, and evaluation
api/            FastAPI application, migrations, and integration tests
web/            React study interface
infra/          Container definitions and deployment configuration
docs/           Design decisions, event schemas, and operational notes
```

## Roadmap

1. **Foundations:** define review events, recall labels, scheduling contracts, and
   privacy boundaries; scaffold builds and CI; implement and test the C++ baseline.
2. **Usable study loop:** add decks/cards, durable review ingestion, due queues,
   the API, database migrations, and a minimal web interface. Ensure retries cannot
   create duplicate reviews.
3. **Learning pipeline:** collect consented review histories, build reproducible
   features, train a small PyTorch model, and evaluate it against the baseline.
4. **Personalized scheduling:** integrate model scoring, user adaptation, shadow
   evaluation, model versioning, and reliable fallback behavior.
5. **Deployment:** package services, add authentication and ownership enforcement,
   document backups and restores, and deploy a monitored pilot over HTTPS.

## Deployment direction

Start with CPU inference and offline training. A small hosted deployment can run
the web client, API, PostgreSQL, and a separate training job; GPUs are optional for
future training experiments, not a runtime requirement. Choose a hosting provider
after measuring cost and operational needs.

Before exposing real user data, require authentication, per-user authorization,
TLS, managed secrets, database migrations, tested backup/restore procedures,
health checks, and model rollback. Monitor API errors, inference latency, fallback
frequency, and prediction calibration without logging card contents or credentials.

Study history is personal data. Minimize collection, explain training use, obtain
appropriate consent for cross-user training, and provide export/deletion workflows.
Define how deletion affects retained datasets and trained artifacts before
collecting production training data. Never commit real review histories or secrets.

## Development

There are no build or run commands yet because implementation has not begun.
Add verified setup and test instructions alongside the first working components.
See [AGENTS.md](AGENTS.md) for implementation guidance and project constraints.

## License

A license has not been selected. Public repository visibility alone does not
grant an open-source license.
