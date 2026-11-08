"""Small CPU-compatible models with explicitly monotone time decay."""

import math

import torch
from torch import nn


class RecallModel(nn.Module):
    def __init__(self, users: int, hidden: int = 16, personalized: bool = True):
        super().__init__()
        self.hidden = hidden
        self.personalized = personalized
        self.history = nn.Sequential(nn.Linear(3, hidden), nn.Tanh(), nn.Linear(hidden, 1))
        self.user_effect = nn.Embedding(users + 1, 1, padding_idx=0)
        nn.init.zeros_(self.user_effect.weight)

    def forward(self, history, elapsed, user):
        log_half_life = self.history(history).squeeze(-1)
        if self.personalized:
            log_half_life = log_half_life + self.user_effect(user).squeeze(-1)
        half_life = log_half_life.clamp(-6, 12).exp()
        return -math.log(2) * elapsed / half_life  # log P(success)

    def penalty(self):
        return self.user_effect.weight[1:].square().mean()


class SharedDecay(nn.Module):
    def __init__(self):
        super().__init__()
        self.log_half_life = nn.Parameter(torch.tensor(math.log(5.0)))

    def forward(self, history, elapsed, user):
        return -math.log(2) * elapsed / self.log_half_life.clamp(-6, 12).exp()

    def penalty(self):
        return self.log_half_life.new_zeros(())


def loss(log_probability, target):
    # log(1-p) via expm1 avoids cancellation near p=1; never take log(0).
    log_probability = log_probability.clamp(max=-1e-7)
    return -(
        target * log_probability + (1 - target) * torch.log(-torch.expm1(log_probability))
    ).mean()


def predict(model, batch):
    model.eval()
    with torch.no_grad():
        return model(batch["history"], batch["elapsed"], batch["user"]).exp()
