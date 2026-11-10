from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictStr

from practice.models import (
    Attempt,
    CodingProblem,
    Difficulty,
    Exercise,
    Flashcard,
    LearningItem,
    Outcome,
    Timing,
)

NonnegativeSeconds = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
PositiveSeconds = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CollectionCreate(Input):
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)]


class ProblemInput(Input):
    type: Literal["coding_problem"]
    url: Annotated[StrictStr, Field(min_length=1, max_length=2048)]
    difficulty: Difficulty | None = None


class CardInput(Input):
    type: Literal["flashcard"]
    front: Annotated[StrictStr, Field(min_length=1, max_length=20_000)]
    back: Annotated[StrictStr, Field(min_length=1, max_length=20_000)]


class ExerciseInput(Input):
    type: Literal["exercise"]
    instructions: Annotated[StrictStr, Field(min_length=1, max_length=20_000)]


class ItemCreate(Input):
    collection_id: UUID
    title: Annotated[StrictStr, Field(min_length=1, max_length=300)]
    content: Annotated[ProblemInput | CardInput | ExerciseInput, Field(discriminator="type")]
    target_seconds: PositiveSeconds | None = None
    tags: Annotated[list[StrictStr], Field(max_length=50)] = Field(default_factory=list)

    def domain(self, identity: UUID, owner: UUID, created_at: datetime, archived=False):
        if isinstance(self.content, ProblemInput):
            content = CodingProblem(self.content.url, self.content.difficulty)
        elif isinstance(self.content, CardInput):
            content = Flashcard(self.content.front, self.content.back)
        else:
            content = Exercise(self.content.instructions)
        return LearningItem(
            identity,
            owner,
            self.collection_id,
            self.title,
            content,
            created_at,
            self.target_seconds,
            tuple(self.tags),
            archived,
        )


class TimingInput(Input):
    measured_seconds: NonnegativeSeconds | None = None
    corrected_seconds: NonnegativeSeconds | None = None
    correction_reason: Annotated[StrictStr, Field(min_length=1, max_length=500)] | None = None


class AttemptCreate(Input):
    id: UUID
    occurred_at: AwareDatetime
    outcome: Outcome
    timing: TimingInput = Field(default_factory=TimingInput)
    confidence: Annotated[int, Field(strict=True, ge=1, le=5)] | None = None

    def domain(self, owner: UUID, item: UUID):
        return Attempt(
            self.id,
            owner,
            item,
            self.occurred_at,
            self.outcome,
            Timing(**self.timing.model_dump()),
            self.confidence,
        )
