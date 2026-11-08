import math
import unittest

import torch

from ml.metrics import score
from ml.model import RecallModel, SharedDecay, loss


class ModelTests(unittest.TestCase):
    def test_bounded_monotone_recall(self):
        torch.manual_seed(3)
        for model in (RecallModel(3), SharedDecay()):
            history = torch.tensor([[1.0, 0.5, 0.5]]).repeat(100, 1)
            elapsed = torch.linspace(0, 1000, 100)
            users = torch.zeros(100, dtype=torch.long)
            probability = model(history, elapsed, users).exp()
            self.assertTrue(torch.isfinite(probability).all())
            self.assertTrue(((probability >= 0) & (probability <= 1)).all())
            self.assertEqual(float(probability[0].detach()), 1)
            self.assertTrue((probability[1:] <= probability[:-1]).all())

    def test_unknown_user_effect_is_zero_after_optimization(self):
        model = RecallModel(3)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        for _ in range(3):
            optimizer.zero_grad()
            objective = (
                loss(
                    model(torch.ones(4, 3), torch.ones(4), torch.tensor([0, 1, 2, 3])),
                    torch.ones(4),
                )
                + model.penalty()
            )
            objective.backward()
            optimizer.step()
        self.assertEqual(float(model.user_effect.weight[0].detach()), 0)

    def test_stable_loss_and_finite_gradients(self):
        values = torch.tensor([-1e-12, -1000.0, -0.1, -1000.0], requires_grad=True)
        objective = loss(values, torch.tensor([0.0, 1.0, 1.0, 0.0]))
        self.assertTrue(torch.isfinite(objective))
        objective.backward()
        self.assertTrue(torch.isfinite(values.grad).all())

    def test_known_metrics_and_validation(self):
        metrics = score([0, 1], [0.1, 0.9])
        self.assertAlmostEqual(metrics["brier_score"], 0.01)
        self.assertAlmostEqual(metrics["log_loss"], -math.log(0.9))
        self.assertEqual(sum(b["count"] for b in metrics["calibration"]), 2)
        for targets, probabilities in (
            ([], []),
            ([0], [float("nan")]),
            ([0], [1.1]),
            ([0], []),
            ([2], [0.5]),
        ):
            with self.assertRaises(ValueError):
                score(targets, probabilities)


if __name__ == "__main__":
    unittest.main()
