"""Versioned JSON weights: no pickle deserialization or executable model files."""

import json
import os
import tempfile
from pathlib import Path

import torch

from ml.data import FEATURE_VERSION, FEATURES
from ml.model import RecallModel

ARTIFACT_VERSION = 1
MAX_ARTIFACT_BYTES = 5_000_000


def _json_text(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n"


def write_json(path: Path, payload: dict):
    encoded = _json_text(payload)
    staging = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".epoch-ml-", delete=False
        ) as output:
            staging = Path(output.name)
            output.write(encoded)
        # Atomic no-replace publication, matching the simulator's file-safety contract.
        os.link(staging, path)
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)


def save_artifact(path: Path, model: RecallModel, users: dict[int, int]):
    if any(type(user) is not int or type(index) is not int for user, index in users.items()):
        raise ValueError("vocabulary IDs and indices must be integers")
    if users != {user: index + 1 for index, user in enumerate(sorted(users))}:
        raise ValueError("vocabulary must map sorted users to consecutive indices from one")
    payload = {
        "artifact_version": ARTIFACT_VERSION,
        "feature_version": FEATURE_VERSION,
        "features": list(FEATURES),
        "hidden": model.hidden,
        "personalized": model.personalized,
        "user_ids": sorted(users),
        "weights": {
            name: tensor.detach().cpu().tolist() for name, tensor in model.state_dict().items()
        },
    }
    # Apply exactly the loader's schema, architecture, and weight checks before
    # publishing, so a successful export cannot leave an unloadable artifact.
    _model_from_payload(payload)
    if len(_json_text(payload).encode("utf-8")) > MAX_ARTIFACT_BYTES:
        raise ValueError("model artifact exceeds 5 MB")
    write_json(path, payload)


def load_artifact(path: Path) -> tuple[RecallModel, dict[int, int]]:
    # Keep allocation bounded before constructing tensors or embedding tables.
    with path.open("rb") as source:
        encoded = source.read(MAX_ARTIFACT_BYTES + 1)
    if len(encoded) > MAX_ARTIFACT_BYTES:
        raise ValueError("model artifact exceeds 5 MB")

    def reject_constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")

    payload = json.loads(encoded, parse_constant=reject_constant)
    return _model_from_payload(payload)


def _model_from_payload(payload: dict) -> tuple[RecallModel, dict[int, int]]:
    expected_keys = {
        "artifact_version",
        "feature_version",
        "features",
        "hidden",
        "personalized",
        "user_ids",
        "weights",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise ValueError("invalid artifact fields")
    if (
        type(payload["artifact_version"]) is not int
        or payload["artifact_version"] != ARTIFACT_VERSION
        or type(payload["feature_version"]) is not int
        or payload["feature_version"] != FEATURE_VERSION
        or payload["features"] != list(FEATURES)
    ):
        raise ValueError("unsupported artifact/feature schema")
    if type(payload["hidden"]) is not int or not 1 <= payload["hidden"] <= 64:
        raise ValueError("unsupported hidden dimension")
    ids = payload["user_ids"]
    if (
        not isinstance(ids, list)
        or not 1 <= len(ids) <= 10_000
        or any(type(user) is not int or user < 0 for user in ids)
        or ids != sorted(set(ids))
        or type(payload["personalized"]) is not bool
    ):
        raise ValueError("invalid model configuration or vocabulary")
    users = {user: index + 1 for index, user in enumerate(ids)}
    # Template initialization must not perturb the caller's training RNG state.
    with torch.random.fork_rng(devices=[]):
        model = RecallModel(len(users), payload["hidden"], payload["personalized"])
    expected = model.state_dict()
    if not isinstance(payload["weights"], dict) or set(payload["weights"]) != set(expected):
        raise ValueError("unexpected weight names")
    weights = {}
    for name, template in expected.items():
        try:
            value = torch.tensor(payload["weights"][name], dtype=torch.float32)
        except (ValueError, TypeError, RuntimeError) as error:
            raise ValueError(f"invalid weights: {name}") from error
        if value.shape != template.shape or not torch.isfinite(value).all():
            raise ValueError(f"invalid weight shape or values: {name}")
        weights[name] = value
    if torch.count_nonzero(weights["user_effect.weight"][0]):
        raise ValueError("unknown-user effect must be zero")
    model.load_state_dict(weights, strict=True)
    model.eval()
    return model, users
