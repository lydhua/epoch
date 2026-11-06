# Epoch

A spaced-repetition study tool that learns how you forget.

Epoch aims to support spaced practice for any kind of learning: coding problems,
concepts, flashcards, exercises, and other skills. The initial use case is revisiting
LeetCode-style problems, not a flashcard-only workflow. A PyTorch model will learn
from each learner's practice history instead of assigning everyone the same
forgetting curve, adapting as more evidence becomes available.

Modern Anki already offers learned scheduling through FSRS. Epoch's intended
distinction is support for coding/general practice, timing-aware outcomes, and
activity-specific learning goals—not a claim that existing tools lack ML.

**Status:** early implementation. A C++20 synthetic-session generator, native and
CLI integration tests, and GitHub Actions CI configuration are present. The
PyTorch model, application, frontend, and deployment are not implemented yet.
See [GitHub Actions](https://github.com/lydhua/epoch/actions/workflows/ci.yml) for
CI results, plus the
[experiment specification](docs/experiment-v1.md) and
[product requirements](docs/product-v1.md).
The [mastery and spacing research note](docs/research/mastery-and-spacing.md)
separates supporting evidence from proposed product heuristics.

Prioritize meaningful tests, clear architecture, honest measurements, and a usable
deployment rather than infrastructure for its own sake.

## Goals

- Organize learning items into collections and revisit them when due.
- Start with linked coding problems and self-reported attempts; support flashcards
  and other activity types without making front/back text a universal requirement.
- Predict recall probability from elapsed time and previous review outcomes.
- Learn a user's forgetting behavior while accounting for differences between items
  and kinds of practice.
- Choose review intervals around a configurable target retention rate.
- Compare the learned scheduler with a transparent baseline before claiming gains.
- Deploy a usable web application with portable, reproducible infrastructure.
- Support optional practice timing, user feedback, and long-term maintenance
  reviews after an item is marked learned, especially for medium/hard problems.

The first release will focus on one primary workflow: add a problem or learning
item, attempt it, record the outcome, and schedule the next practice session.
Broad support means an extensible data model, not implementing every learning
format at once. Automated code execution/grading, LeetCode account integration,
Anki import/export, offline synchronization, and native mobile clients are later
options. Compatibility with Anki's scheduling or collection format is not implied.

## Original foundation

The original project concept paired a **C++ simulator generating 500,000 synthetic
learning sessions with individualized forgetting curves** with a **PyTorch neural
network trained to predict recall probability from simulated session histories**.
The simulator is now implemented; the PyTorch training stage is next. The planned
500,000-session scale is supported by the CLI but is not a claimed completed
training experiment.

Reproduce it with configurable population parameters, fixed seeds, explicit
session/event definitions, and recorded dataset provenance. Use it to bootstrap
experiments and test recovery of simulated forgetting behavior. Success on
synthetic histories does not establish accuracy on real learners or transfer from
flashcard recall to problem-solving ability.

## Proposed stack

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Scheduling service | Python initially | Interval selection, maintenance reviews, and safe fallback policy |
| Simulation | C++20 | Reproducible synthetic learning sessions and individualized forgetting curves |
| Learning | Python, PyTorch | Recall prediction, training, calibration, and model evaluation |
| API | Python, FastAPI | Authentication, collections, learning items, attempt ingestion, and scheduling orchestration |
| Database | PostgreSQL | User-owned content, append-only review events, and scheduling state |
| Web client | TypeScript, React, Vite | Learning collections, due practice, and attempt recording |
| Packaging and deployment | Docker, Docker Compose | Reproducible local services and a path to hosted deployment |

The C++ simulator gives native code a substantive role without prematurely
requiring native bindings. Scheduling and PyTorch inference will initially stay
in Python. A C++ scheduling library, pybind11 bindings, or native inference runtime
can be evaluated if profiling demonstrates a need. This intentionally simplifies
the original native-core proposal.

```text
React web client
       |
   FastAPI ---------------- PostgreSQL
       |
 Python scheduling service --- PyTorch recall model
                                      ^
                                      |
 C++ simulator -> dataset -> Offline training worker
```

## Learning and scheduling design

### Record the evidence

Use a shared learning-item identity with a type and type-specific metadata:
a coding problem may have a URL, tags, and difficulty; a flashcard may have front
and back text; another exercise may have instructions and a completion rubric.
Keep review events and scheduling independent of the content format.

Each review/attempt should record a unique event ID, user and item identifiers, UTC
timestamp, elapsed time since the previous review, outcome, response duration,
and the scheduler/model version that proposed the review. Preserve the learner's
original rating separately from any derived recall label. A rating-to-label
mapping must be explicit and versioned; self-reported difficulty is an imperfect
proxy for recall, not objective ground truth.

For coding practice, preserve whether the learner solved independently, used
hints, consulted a solution, or could not solve it, along with time spent when
available. Define success per activity type: remembering an approach, producing
a correct solution, and answering a flashcard are different targets. Do not
silently collapse them into interchangeable recall labels. Self-reported attempts
are sufficient initially; Epoch does not need to execute submitted code.

### Predict recall

Start with a small PyTorch model that predicts
`P(success on the defined task | elapsed time, practice history, user, item, activity type)`.
Use a time-dependent decay parameterization with non-increasing recall probability
as elapsed time increases, rather than unconstrained interval predictions.
Candidate features include prior successes and failures, previous intervals,
review count, activity type, and learned user/item effects. Do not require item
content or submitted code for the first model. Evaluate calibration separately
for each supported activity type rather than assuming one universal recall target.

Use a shared population model with regularized user-level adaptation so that
personalization does not depend on training an independent model for every user.
New users and items back off to shared parameters. Before a validated model and
sufficient data exist, use a documented deterministic bootstrap scheduler. This
fallback is necessary for cold start; it is not the intended long-term source of
personalized intervals.

### Choose a review time

Given an experimentally chosen target retention probability, select the
longest supported interval whose predicted recall remains above the target.
Enforce minimum/maximum intervals and sensible handling of failed or overdue
reviews. Fall back safely when the model is unavailable, produces invalid output,
or lacks sufficient evidence. Store the reason for each scheduling decision.
The earlier 90% proposal is not an established default for coding practice.
Learned items enter maintenance, not permanent removal. Combine independent
success, timing, and user feedback only through an explicit, evaluated policy.

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
simulator/      C++ synthetic session generator and simulation tests
ml/             PyTorch models, features, training, and evaluation
api/            FastAPI application, migrations, and integration tests
web/            React study interface
infra/          Container definitions and deployment configuration
docs/           Design decisions, event schemas, and operational notes
```

## Roadmap

1. **Foundations:** define generic learning items, activity-specific outcomes,
   review events, scheduling contracts, and privacy boundaries; scaffold builds
   and CI; implement and test a transparent baseline scheduler in Python.
2. **Simulation and model prototype:** build the C++ generator targeting 500,000
   synthetic learning sessions with individualized forgetting curves; train and
   evaluate a PyTorch recall model on their histories, keeping simulated learners
   and future events out of training where required by the evaluation split.
3. **Usable practice loop:** add collections, linked coding problems, manual attempt
   recording, durable review ingestion, due queues, the API, migrations, and a
   minimal web interface. Ensure retries cannot create duplicate reviews. Add
   flashcards and other activity types incrementally through the shared item model.
4. **Real-data validation:** collect consented practice histories, validate outcome
   definitions by activity type, and compare model predictions with the baseline.
   Measure the simulation-to-real gap before enabling learned scheduling.
5. **Personalized scheduling:** integrate model scoring, user adaptation, shadow
   evaluation, model versioning, and reliable fallback behavior.
6. **Deployment:** package services, add authentication and ownership enforcement,
   document backups and restores, and deploy a monitored pilot over HTTPS.

## Deployment direction

Start with CPU inference and offline training. A small hosted deployment can run
the web client, API, PostgreSQL, and a separate training job; GPUs are optional for
future training experiments, not a runtime requirement. Choose a hosting provider
after measuring cost and operational needs.

Before exposing real user data, require authentication, per-user authorization,
TLS, managed secrets, database migrations, tested backup/restore procedures,
health checks, and model rollback. Monitor API errors, inference latency, fallback
frequency, and prediction calibration without logging learning content, submitted
code, or credentials.

Study history is personal data. Minimize collection, explain training use, obtain
appropriate consent for cross-user training, and provide export/deletion workflows.
Define how deletion affects retained datasets and trained artifacts before
collecting production training data. Never commit real review histories or secrets.

## Development

Requirements: macOS/Linux, a C++20 compiler (Clang or GCC), CMake 3.20+, and Python
3.9+ for CLI integration tests. There are no third-party C++ dependencies. Output
requires a filesystem supporting hard links for atomic, no-overwrite publication.

Optional pinned development tools (including CMake if not installed):

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel 2
ctest --test-dir build --output-on-failure
```

For AddressSanitizer and UndefinedBehaviorSanitizer checks with Clang/GCC:

```sh
cmake -S . -B build-sanitized -DCMAKE_BUILD_TYPE=Debug -DEPOCH_SANITIZERS=ON
cmake --build build-sanitized --parallel 2
ctest --test-dir build-sanitized --output-on-failure
```

Generate a small dataset (the output path must not already exist):

```sh
mkdir -p data
./build/epoch-simulate --output data/sessions.csv --sessions 1000 --users 100 --reviews 8 --seed 42
```

The scale target uses `--sessions 500000`: at eight reviews each this produces
4,000,000 CSV rows, so allow disk space and keep generated data out of Git.
A session is one learner-item trajectory, not one individual review.
Generation publishes only complete files and rejects existing files or symlinks,
including when writers race. Handled failures clean up staging; a forced kill may
leave a hidden `.epoch-simulate-*` directory but no partial final dataset. See the
[experiment specification](docs/experiment-v1.md) for filesystem/durability limits.

Formatting/lint checks, after installing the development tools:

```sh
find simulator -type f \( -name '*.cpp' -o -name '*.hpp' \) -exec clang-format --dry-run --Werror {} +
ruff check simulator/tests
ruff format --check simulator/tests
```

CI configuration runs formatting/lint checks, GCC/Clang Debug/Release builds,
unit/CLI tests, and a separate sanitizer job. CD will be added with the first
deployable service, including staging smoke tests, production approval, and
rollback—not a placeholder deploy.
See [AGENTS.md](AGENTS.md) for implementation guidance and project constraints.

## License

A license has not been selected. Public repository visibility alone does not
grant an open-source license.
