"""Prediction quality, calibration, and history-length slices (not policy gains)."""

import math


def score(targets, probabilities):
    if not targets or len(targets) != len(probabilities):
        raise ValueError("metrics need equal, nonempty target/prediction arrays")
    if any(y not in (0, 1) for y in targets):
        raise ValueError("targets must be binary")
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities):
        raise ValueError("probabilities must be finite and in [0,1]")
    n = len(targets)
    pairs = list(zip(targets, probabilities))
    clipped = [(y, min(1 - 1e-7, max(1e-7, p))) for y, p in pairs]
    bins = []
    for index in range(10):
        members = [(y, p) for y, p in pairs if min(9, int(p * 10)) == index]
        bins.append(
            {
                "lower": index / 10,
                "upper": (index + 1) / 10,
                "count": len(members),
                "predicted": sum(p for _, p in members) / len(members) if members else None,
                "observed": sum(y for y, _ in members) / len(members) if members else None,
            }
        )
    return {
        "count": n,
        "log_loss": -sum(y * math.log(p) + (1 - y) * math.log1p(-p) for y, p in clipped) / n,
        "brier_score": sum((p - y) ** 2 for y, p in pairs) / n,
        "calibration": bins,
        "ece": sum(b["count"] * abs(b["predicted"] - b["observed"]) for b in bins if b["count"])
        / n,
    }


def evaluate(reviews, probabilities):
    result = score([r.success for r in reviews], probabilities)
    result["by_history_length"] = {}
    for name, low, high in (("0-1", 0, 1), ("2-4", 2, 4), ("5+", 5, 100)):
        selected = [
            (r.success, p) for r, p in zip(reviews, probabilities) if low <= r.index <= high
        ]
        result["by_history_length"][name] = (
            score([y for y, _ in selected], [p for _, p in selected]) if selected else None
        )
    return result
