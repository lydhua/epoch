from datetime import UTC, datetime, timedelta
from uuid import UUID

from practice.models import Attempt, CodingProblem, Difficulty, LearningItem, Outcome

OWNER = UUID(int=1)
ITEM = UUID(int=2)
COLLECTION = UUID(int=3)
START = datetime(2026, 1, 1, tzinfo=UTC)


def item(**changes):
    values = dict(
        id=ITEM,
        owner_id=OWNER,
        collection_id=COLLECTION,
        title="Practice problem",
        content=CodingProblem("https://leetcode.com/problems/two-sum/", Difficulty.MEDIUM),
        created_at=START,
    )
    return LearningItem(**(values | changes))


def attempt(number, *, hours=0, outcome=Outcome.INDEPENDENT, **changes):
    values = dict(
        id=UUID(int=100 + number),
        owner_id=OWNER,
        item_id=ITEM,
        occurred_at=START + timedelta(hours=hours),
        outcome=outcome,
    )
    return Attempt(**(values | changes))
