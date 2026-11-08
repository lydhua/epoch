import json
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

import torch

from ml.artifact import load_artifact, save_artifact, write_json
from ml.data import load_reviews, tensors
from ml.model import RecallModel, predict
from ml.tests.helpers import write_fixture
from ml.train import Config, run_experiment


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.csv = self.root / "sessions.csv"
        write_fixture(self.csv)

    def test_artifact_round_trip_and_no_overwrite(self):
        model = RecallModel(2)
        model_path = self.root / "model.json"
        users = {2: 1, 4: 2}
        save_artifact(model_path, model, users)
        restored, restored_users = load_artifact(model_path)
        batch = tensors(load_reviews(self.csv).reviews, users)
        self.assertEqual(restored_users, users)
        self.assertTrue(torch.equal(predict(model, batch), predict(restored, batch)))
        before = model_path.read_bytes()
        with self.assertRaises(FileExistsError):
            save_artifact(model_path, model, users)
        self.assertEqual(before, model_path.read_bytes())
        self.assertFalse(list(self.root.glob(".epoch-ml-*")))

    def test_development_dependency_pins_match_native_setup(self):
        root = Path(__file__).resolve().parents[2]
        project = tomllib.loads((root / "pyproject.toml").read_text())
        native = (root / "requirements-dev.txt").read_text().splitlines()
        self.assertEqual(sorted(project["dependency-groups"]["dev"]), sorted(native))

    def test_export_rejects_incompatible_models_before_writing(self):
        path = self.root / "invalid.json"
        cases = [
            (RecallModel(2), {7: 1}),
            (RecallModel(2), {7: 1, 9: 2, 11: 3}),
            (RecallModel(0), {}),
            (RecallModel(1, hidden=65), {7: 1}),
            (RecallModel(1), {-1: 1}),
            (RecallModel(1), {7: True}),
        ]
        nonzero_fallback = RecallModel(1)
        with torch.no_grad():
            nonzero_fallback.user_effect.weight[0].fill_(1)
        cases.append((nonzero_fallback, {7: 1}))
        for model, users in cases:
            with self.subTest(users=users, hidden=model.hidden):
                with self.assertRaises(ValueError):
                    save_artifact(path, model, users)
                self.assertFalse(path.exists())
                self.assertFalse(list(self.root.glob(".epoch-ml-*")))

    def test_artifact_validation_preserves_training_rng(self):
        model = RecallModel(2)
        before = torch.get_rng_state().clone()
        path = self.root / "model.json"
        save_artifact(path, model, {2: 1, 4: 2})
        self.assertTrue(torch.equal(before, torch.get_rng_state()))
        load_artifact(path)
        self.assertTrue(torch.equal(before, torch.get_rng_state()))

    def test_rejects_incompatible_and_malformed_artifacts(self):
        model_path = self.root / "model.json"
        save_artifact(model_path, RecallModel(2), {2: 1, 4: 2})
        original = model_path.read_text()
        changes = [
            ("feature_version", 99),
            ("features", ["oracle_half_life_days"]),
            ("hidden", 10000000),
            ("user_ids", [2, 2]),
            ("weights", {}),
        ]
        for field, value in changes:
            payload = json.loads(original)
            payload[field] = value
            model_path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                load_artifact(model_path)
        payload = json.loads(original)
        payload["weights"]["user_effect.weight"][0] = [1.0]
        model_path.write_text(json.dumps(payload))
        with self.assertRaises(ValueError):
            load_artifact(model_path)
        with self.assertRaises(ValueError):
            write_json(self.root / "invalid.json", {"value": float("nan")})
        self.assertFalse((self.root / "invalid.json").exists())

    def test_reproducible_training_smoke(self):
        config = Config(epochs=3, batch_size=32)
        first = run_experiment(self.csv, self.root / "first", config)
        second = run_experiment(self.csv, self.root / "second", config)
        self.assertTrue(first["synthetic_only"])
        self.assertEqual(first["metrics"], second["metrics"])
        self.assertEqual(first["model_sha256"], second["model_sha256"])
        self.assertEqual(first["training"], second["training"])
        self.assertEqual(
            set(first["metrics"]["warm_test"]),
            {"constant", "shared_decay", "history_only", "personalized"},
        )
        model, users = load_artifact(self.root / "first" / "model.json")
        predictions = predict(model, tensors(load_reviews(self.csv).reviews, users))
        self.assertTrue(torch.isfinite(predictions).all())
        with self.assertRaises(ValueError):
            run_experiment(self.csv, self.root / "first", config)

    def test_invalid_inputs_do_not_create_run_directory(self):
        for config in (
            Config(seed=-1),
            Config(epochs=0),
            Config(epochs=True),
            Config(learning_rate=float("nan")),
            Config(max_rows=1_000_001),
        ):
            with self.assertRaises(ValueError):
                run_experiment(self.csv, self.root / "invalid", config)
            self.assertFalse((self.root / "invalid").exists())
        self.csv.write_text("bad header\n")
        with self.assertRaises(ValueError):
            run_experiment(self.csv, self.root / "invalid", Config(epochs=1))
        self.assertFalse((self.root / "invalid").exists())

    def test_cli_success_and_invalid_configuration(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ml.train",
                "--data",
                str(self.csv),
                "--output",
                str(self.root / "cli"),
                "--epochs",
                "1",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "cli" / "report.json").exists())
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ml.train",
                "--data",
                str(self.csv),
                "--output",
                str(self.root / "invalid"),
                "--epochs",
                "0",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "invalid").exists())


if __name__ == "__main__":
    unittest.main()
