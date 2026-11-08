"""Reproducible CPU experiment: python -m ml.train --help."""

import argparse
import hashlib
import math
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import torch

from ml.artifact import save_artifact, write_json
from ml.data import FEATURE_VERSION, FEATURES, load_reviews, split_reviews, tensors, user_vocabulary
from ml.metrics import evaluate
from ml.model import RecallModel, SharedDecay, loss, predict


@dataclass(frozen=True)
class Config:
    seed: int = 42
    epochs: int = 50
    batch_size: int = 128
    learning_rate: float = 0.01
    user_regularization: float = 0.001
    max_rows: int = 200_000

    def validate(self):
        if any(
            type(value) is not int
            for value in (self.seed, self.epochs, self.batch_size, self.max_rows)
        ):
            raise ValueError("seed, epochs, batch_size, and max_rows must be integers")
        if not 0 <= self.seed <= 2**32 - 1:
            raise ValueError("seed must fit uint32")
        if not 1 <= self.epochs <= 1000 or not 1 <= self.batch_size <= 100_000:
            raise ValueError("epochs must be 1..1000 and batch_size 1..100000")
        if not math.isfinite(self.learning_rate) or not 0 < self.learning_rate <= 1:
            raise ValueError("learning_rate must be in (0,1]")
        if not math.isfinite(self.user_regularization) or not 0 <= self.user_regularization <= 1:
            raise ValueError("user_regularization must be in [0,1]")
        if not 1 <= self.max_rows <= 1_000_000:
            raise ValueError("max_rows must be 1..1000000; loader is in-memory")


def fit(model, train, validation, config):
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    generator = torch.Generator().manual_seed(config.seed)
    best_loss = math.inf
    best_state = None
    best_epoch = 0
    for epoch in range(config.epochs):
        model.train()
        order = torch.randperm(len(train["target"]), generator=generator)
        for indices in order.split(config.batch_size):
            optimizer.zero_grad()
            batch = {name: value[indices] for name, value in train.items()}
            log_probability = model(batch["history"], batch["elapsed"], batch["user"])
            objective = loss(log_probability, batch["target"])
            objective = objective + config.user_regularization * model.penalty()
            if not torch.isfinite(objective):
                raise ValueError("training produced a nonfinite loss")
            objective.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0, error_if_nonfinite=True)
            optimizer.step()
        model.eval()
        with torch.no_grad():
            value = float(
                loss(
                    model(validation["history"], validation["elapsed"], validation["user"]),
                    validation["target"],
                )
            )
        if not math.isfinite(value):
            raise ValueError("validation produced a nonfinite loss")
        if value < best_loss:
            best_loss = value
            best_epoch = epoch + 1
            best_state = {name: value.clone() for name, value in model.state_dict().items()}
    model.load_state_dict(best_state)
    return {"selected_epoch": best_epoch, "validation_log_loss": best_loss}


def _git_metadata():
    root = Path(__file__).resolve().parent.parent
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=root, text=True, stderr=subprocess.DEVNULL
            ).strip()
        )
        return {"revision": revision, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"revision": None, "dirty": None}


def run_experiment(csv_path: Path, output_dir: Path, config: Config) -> dict:
    config.validate()
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError("output directory already exists; choose a new run name")
    started = time.perf_counter()
    dataset = load_reviews(csv_path, config.max_rows)
    splits = split_reviews(dataset.reviews, config.seed)
    users = user_vocabulary(splits["train"])
    if len(users) > 10_000:
        raise ValueError("initial artifact format supports at most 10000 training users")
    batches = {name: tensors(rows, users) for name, rows in splits.items()}
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    constant = (sum(r.success for r in splits["train"]) + 0.5) / (len(splits["train"]) + 1)
    models = {}
    training = {}
    for name in ("shared_decay", "history_only", "personalized"):
        torch.manual_seed(config.seed)
        model = (
            SharedDecay()
            if name == "shared_decay"
            else RecallModel(len(users), personalized=name == "personalized")
        )
        training[name] = fit(model, batches["train"], batches["validation"], config)
        models[name] = model
    results = {}
    for split in ("warm_test", "cold_test"):
        rows = splits[split]
        results[split] = {"constant": evaluate(rows, [constant] * len(rows))}
        for name, model in models.items():
            results[split][name] = evaluate(rows, predict(model, batches[split]).tolist())

    # Reserve a fresh run directory; never merge with or overwrite an earlier run.
    # Publication is complete only when report.json exists and its model hash matches.
    output_dir.mkdir(parents=True, exist_ok=False)
    model_path = output_dir / "model.json"
    save_artifact(model_path, models["personalized"], users)
    source_digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        source_digest.update(path.name.encode())
        source_digest.update(path.read_bytes())
    lock = Path(__file__).resolve().parent.parent / "uv.lock"
    report = {
        "report_version": 1,
        "synthetic_only": True,
        "config": asdict(config),
        "feature_version": FEATURE_VERSION,
        "features": list(FEATURES),
        "dataset": {
            "path": str(csv_path.resolve()),
            "sha256": dataset.sha256,
            "rows": len(dataset.reviews),
            "simulator_seed": dataset.simulator_seed,
        },
        "split": {
            name: {
                "rows": len(rows),
                "users": len({r.user for r in rows}),
                "sessions": len({r.session for r in rows}),
            }
            for name, rows in splits.items()
        },
        "split_contract": "whole-user cold holdout; remaining sessions 60/20/20 chronological",
        "cold_contract": "unseen users with rolling prior history; no test-time weight updates",
        "training": training,
        "constant_probability": constant,
        "shared_half_life_days": float(
            models["shared_decay"].log_half_life.detach().clamp(-6, 12).exp()
        ),
        "metrics": results,
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "environment": {
            "python": sys.version,
            "torch": str(torch.__version__),
            "platform": platform.platform(),
            "device": "cpu",
            "threads": 1,
            "git": _git_metadata(),
            "ml_source_sha256": source_digest.hexdigest(),
            "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        },
        "runtime_seconds": time.perf_counter() - started,
    }
    write_json(output_dir / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--max-rows", type=int, default=200_000)
    args = parser.parse_args()
    try:
        report = run_experiment(
            args.data,
            args.output,
            Config(
                seed=args.seed,
                epochs=args.epochs,
                batch_size=args.batch_size,
                max_rows=args.max_rows,
            ),
        )
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(1, f"epoch-ml: {error}\n")
    print(f"Synthetic experiment complete: {args.output / 'report.json'}")
    for split, results in report["metrics"].items():
        for name, metrics in results.items():
            print(
                f"{split:10} {name:14} log_loss={metrics['log_loss']:.4f} "
                f"brier={metrics['brier_score']:.4f}"
            )


if __name__ == "__main__":
    main()
