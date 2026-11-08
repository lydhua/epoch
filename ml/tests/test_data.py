import csv
import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import torch

from ml.data import CSV_COLUMNS, FEATURES, load_reviews, split_reviews, tensors, user_vocabulary
from ml.tests.helpers import write_fixture


class DataTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "data.csv"
        write_fixture(self.path)

    def rewrite(self, rows):
        with self.path.open("w", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    def test_schema_features_and_hash(self):
        data = load_reviews(self.path)
        self.assertEqual(data.sha256, hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(data.simulator_seed, 17)
        self.assertEqual(len(data.reviews), 144)
        users = user_vocabulary(data.reviews)
        batch = tensors(data.reviews, users)
        self.assertEqual(batch["history"].shape, (144, len(FEATURES)))
        self.assertTrue(torch.isfinite(batch["history"]).all())
        # Current result is not a feature. Same evidence + elapsed => same inputs.
        review = data.reviews[-1]
        changed = replace(review, success=1 - review.success, item=999, session=999)
        before, after = tensors([review], users), tensors([changed], users)
        for key in ("history", "elapsed", "user"):
            self.assertTrue(torch.equal(before[key], after[key]))
        self.assertFalse(torch.equal(before["target"], after["target"]))

    def test_diagnostic_and_timing_columns_cannot_enter_features(self):
        before = tensors(load_reviews(self.path).reviews, {})
        with self.path.open() as source:
            rows = list(csv.DictReader(source))
        for row in rows:
            row["oracle_half_life_days"] = "999999"
            row["oracle_recall_probability"] = "0.123"
            row["solve_seconds"] = "99999"
        self.rewrite(rows)
        after = tensors(load_reviews(self.path).reviews, {})
        for key in before:
            self.assertTrue(torch.equal(before[key], after[key]))

    def test_splits_are_disjoint_and_chronological(self):
        reviews = load_reviews(self.path).reviews
        splits = split_reviews(reviews, 42)
        self.assertEqual(splits, split_reviews(reviews, 42))
        keys = {name: {(r.session, r.index) for r in rows} for name, rows in splits.items()}
        self.assertEqual(sum(map(len, keys.values())), len(reviews))
        for name in keys:
            for other in keys:
                if name != other:
                    self.assertFalse(keys[name] & keys[other])
        cold_users = {r.user for r in splits["cold_test"]}
        for name in ("train", "validation", "warm_test"):
            self.assertFalse(cold_users & {r.user for r in splits[name]})
        for session in {r.session for r in splits["train"]}:
            history = {
                name: [r.index for r in rows if r.session == session]
                for name, rows in splits.items()
            }
            self.assertLess(max(history["train"]), min(history["validation"]))
            self.assertLess(max(history["validation"]), min(history["warm_test"]))
        vocabulary = user_vocabulary(splits["train"])
        self.assertTrue(
            torch.equal(
                tensors(splits["cold_test"], vocabulary)["user"],
                torch.zeros(len(splits["cold_test"]), dtype=torch.long),
            )
        )

    def test_rejects_invalid_rows(self):
        changes = [
            ("success", "2"),
            ("elapsed_days", "nan"),
            ("elapsed_days", "-1"),
            ("time_days", "inf"),
            ("prior_successes", "99"),
            ("review_index", "4"),
            ("schema_version", "2"),
            ("seed", "18"),
            ("user_id", "99"),
        ]
        original = self.path.read_bytes()
        for key, value in changes:
            with self.subTest(key=key):
                self.path.write_bytes(original)
                with self.path.open() as source:
                    rows = list(csv.DictReader(source))
                rows[1][key] = value
                self.rewrite(rows)
                with self.assertRaises(ValueError):
                    load_reviews(self.path)
        self.path.write_bytes(original)
        with self.assertRaises(ValueError):
            load_reviews(self.path, max_rows=10)

    def test_rejects_elapsed_underflow_before_tensor_conversion(self):
        reviews = load_reviews(self.path).reviews
        with self.path.open() as source:
            rows = list(csv.DictReader(source))
        for row in rows:
            row["elapsed_days"] = "1e-50"
            row["time_days"] = str((int(row["review_index"]) + 1) * 1e-50)
        self.rewrite(rows)
        with self.assertRaisesRegex(ValueError, "positive in float32"):
            load_reviews(self.path)
        for elapsed in (1e-50, 0.0, -1.0, float("nan"), float("inf")):
            with self.subTest(elapsed=elapsed):
                with self.assertRaisesRegex(ValueError, "positive in float32"):
                    tensors([replace(reviews[0], elapsed=elapsed)], {})

    def test_rejects_header_empty_truncated_and_reordered_inputs(self):
        original = self.path.read_text()
        for contents in (
            "",
            original.replace("schema_version", "wrong", 1),
            original + "1,17,999\n",
        ):
            self.path.write_text(contents)
            with self.assertRaises(ValueError):
                load_reviews(self.path)
        self.path.write_text(original)
        with self.path.open() as source:
            rows = list(csv.DictReader(source))
        rows[0], rows[1] = rows[1], rows[0]
        self.rewrite(rows)
        with self.assertRaises(ValueError):
            load_reviews(self.path)

    def test_rejects_insufficient_users_and_short_histories(self):
        write_fixture(self.path, users=2)
        with self.assertRaises(ValueError):
            split_reviews(load_reviews(self.path).reviews, 42)
        write_fixture(self.path, reviews=3)
        with self.assertRaises(ValueError):
            split_reviews(load_reviews(self.path).reviews, 42)


if __name__ == "__main__":
    unittest.main()
