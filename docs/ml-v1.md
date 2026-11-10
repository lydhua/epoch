# ML v1: reproducible synthetic recall prediction

This is an offline CPU experiment, not an application scheduler or a claim about
real learners. The first implementation supports Python 3.12 with locked PyTorch
and NumPy dependencies. Linux uses PyTorch's CPU wheel index to avoid pulling in
CUDA runtimes; local validation currently uses Apple Silicon macOS.

## Components

- `ml/data.py`: schema validation, byte-level dataset hashing, splits, vocabulary,
  and explicit prediction-time features.
- `ml/model.py`: shared decay and small history-conditioned half-life models.
- `ml/train.py`: seeded training, validation-only checkpoint selection, evaluation,
  and report generation.
- `ml/metrics.py`: log loss, Brier score, calibration bins/ECE, and history slices.
- `ml/artifact.py`: versioned JSON weights and validated reload without pickle.
- `ml/tests/`: small synthetic fixtures and fast regression tests.

## Inputs and leakage boundaries

The loader requires the exact simulator-v1 header and validates grouped/increasing
sessions, sequential review indices, stable session ownership, binary outcomes,
finite time values, and success counts consistent with prior outcomes.
Positive delays must also remain finite and positive when converted to float32;
underflowing inputs are rejected rather than silently treated as zero time.
The loader hashes the same bytes it parses, rather than reopening the dataset
later. Incomplete rows are rejected. Without an external generation manifest it
cannot detect truncation
that removes only complete rows/sessions and otherwise leaves a valid dataset.

The network receives only `log1p(review_index)`, `log1p(prior_successes)`, and
`log1p(prior_failures)`. Elapsed days enter only the decay equation. User IDs index
a vocabulary fitted from training rows; item/session IDs are never numeric model
features. Current `success` is the target. Current solve duration, diagnostic
`oracle_*` values, future outcomes, and card/problem text are not input features.
Timing-aware interview objectives remain separate future work.

## Splits

Users are sorted, shuffled with an isolated seeded Python RNG, and 20% (rounded
down, at least one) are reserved entirely for cold evaluation. At least three
users and five reviews per session are required. Remaining sessions are split
chronologically: first 60% training, next approximately 20% validation, final
approximately 20% warm test, with at least one validation/test event each.

These are **session-relative**, not global calendar-time splits: the simulator
does not provide a shared calendar across sessions. User effects are constant
within the simulator population; future real-data evaluation needs a global
time-aware split before making deployment claims.

Validation selects the checkpoint; tests do not select weights or hyperparameters.
Cold users never enter training, validation, or the learned vocabulary. Cold-test
features may include their own previous outcomes as they become available: this
is rolling-history evaluation on unseen users, not exclusively zero-history
prediction. No model weights are updated during evaluation. The same principle
allows earlier validation/test observations to inform later review-count features.

## Models and training

1. **Constant:** smoothed training success rate.
2. **Shared decay:** one fitted half-life for the whole training set.
3. **History-only:** a three-input, 16-hidden-unit Tanh network predicting log
   half-life; a non-personalized neural ablation.
4. **Personalized:** the same network plus an L2-regularized scalar user effect.

`P(success) = exp(-ln(2) * elapsed_days / half_life_days)`. Log half-life is bounded
to `[-6, 12]` for numerical safety; holding history/user fixed, probability cannot
increase with elapsed time. Index zero is the unseen-user fallback, with its
effect fixed at zero. New users still benefit from the shared history network.

Training uses Adam, shuffled minibatches, gradient clipping, fixed seeds,
deterministic PyTorch operations, and one CPU thread. Checkpoints are selected on
validation negative log likelihood. Reported log loss clips probabilities at
`1e-7` and `1-1e-7`; Brier score uses raw predictions. Calibration uses ten fixed
bins; sparse bins should not be overinterpreted. Empty history slices are null,
not zero-error claims. Exact results may differ across platforms/toolchains.

## Commands and outputs

From the repository root, after generating the CSV and installing uv:

```sh
uv sync --locked
uv run --frozen python -m unittest discover -s ml/tests -v
uv run --frozen python -m ml.train --data data/sessions.csv --output artifacts/run-001 --epochs 50
```

Use `--help` for seed, batch-size, and row-cap options. Programmatic `Config` also
sets learning rate and user regularization. The loader is in-memory with a default
200,000-row cap; an explicit override is capped at one million. This is not an
out-of-core four-million-row trainer. Use small datasets before scaling.

Each fresh run directory contains:

- `model.json`: model/feature versions, exact feature names, architecture, training
  user vocabulary, and floating-point weights. Loading rejects incompatible
  schemas, invalid dimensions, nonfinite values, and a nonzero unknown-user effect.
  Export applies the same validation before writing, including model/vocabulary
  compatibility, so invalid inputs cannot publish an unloadable model file.
- `report.json`: configuration, dataset hash/seed, split sizes, selected epochs,
  all baseline/test metrics, model hash, Python/PyTorch/platform versions, source
  fingerprint, dependency-lock hash, Git revision/dirty flag, and runtime.

Files publish atomically without overwriting existing paths. `report.json` is
written last; a directory without it is not a completed run. Verify its model hash
before relying on an artifact. Training failures before output reservation leave
no run directory; later failures can leave an incomplete directory for inspection.
These guarantees do not imply power-loss durability. Data and artifacts are ignored
by Git. Keep the simulator command, generator version, and dataset hash with your
dataset; simulator options cannot all be recovered from the CSV alone.

Example reload for a trusted, locally generated artifact and validated reviews:

```python
from pathlib import Path
from ml.artifact import load_artifact
from ml.data import load_reviews, tensors
from ml.model import predict

model, users = load_artifact(Path("artifacts/run-001/model.json"))
reviews = load_reviews(Path("data/sessions.csv")).reviews
probabilities = predict(model, tensors(reviews, users))
```

## Evidence and next experiments

A local smoke experiment used 1,000 C++ sessions, 100 users, eight reviews each,
simulator/training seed 42, and 50 epochs. It exercised generation through artifact
reload and evaluation. It is not a multi-seed benchmark or evidence of real-user
benefit. Inspect locally generated reports rather than treating a single score as
a stable result. Compare the personalized model to the history-only ablation, not
just a weak constant baseline; cold-user gains are not guaranteed.

Next evaluate multiple seeds, shifted learner populations, changed learning/decay
assumptions, and learning curves versus history size. Only then consider real,
consented practice data and prospective scheduling evaluation. Production fallback,
model-assisted maintenance policy, and deployment are not implemented here.
The separate [baseline/API adapter](api-v1.md) now provides the initial persistent
practice loop; its frontend and timer UI remain future work.
