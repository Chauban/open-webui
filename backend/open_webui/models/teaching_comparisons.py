"""Private editable workbenches, immutable comparisons and saved combinations."""

from typing import Literal

from open_webui.internal.db import Base, JSONField
from open_webui.models.teaching_trials import AiCandidate, StrictModel
from pydantic import Field, model_validator
from sqlalchemy import BigInteger, Column, Integer, Text, UniqueConstraint


class WorkInput(StrictModel):
    comparison_mode: Literal['models', 'prompts'] = 'models'
    title: str = Field(min_length=1, max_length=1000)
    description: str = Field(min_length=1, max_length=65000)
    candidates: list[AiCandidate] = Field(min_length=1, max_length=3)
    sample: str = Field(default='', max_length=200000)

    @model_validator(mode='after')
    def comparison_contract(self):
        if not self.title.strip() or not self.description.strip():
            raise ValueError('Title and requirements are required')
        if self.comparison_mode == 'prompts':
            if len(self.candidates) != 2:
                raise ValueError('Prompt comparison requires exactly two candidates')
            settings = [a.model_dump(exclude={'prompt'}) for a in self.candidates]
            if settings[0] != settings[1]:
                raise ValueError('Prompt comparison must use identical model settings')
            return self
        if len({a.model_id for a in self.candidates}) != len(self.candidates):
            raise ValueError('Choose distinct models')
        if len({a.prompt for a in self.candidates}) != 1:
            raise ValueError('Comparison models must share one prompt')
        return self


class OpenWorkbench(StrictModel):
    trial_id: str
    preparation_id: str


class SaveWorkbench(StrictModel):
    expected_revision: int = Field(gt=0)
    payload: WorkInput


class RunComparison(StrictModel):
    expected_revision: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=128)
    source_trial_id: str | None = None
    source_sequence: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def source_pair(self):
        if (self.source_trial_id is None) != (self.source_sequence is None):
            raise ValueError('Select a completed source node')
        return self


class SavePlan(StrictModel):
    trial_id: str
    name: str = Field(min_length=1, max_length=200)


class AdoptPlan(StrictModel):
    expected_revision: int = Field(gt=0)
    include_task: bool = False
    idempotency_key: str = Field(min_length=8, max_length=128)


class TeachingWorkbench(Base):
    __tablename__ = 'teaching_workbench'
    id = Column(Text, primary_key=True)
    owner_id = Column(Text, nullable=False)
    preparation_id = Column(Text, nullable=False)
    seed_trial_id = Column(Text, nullable=False)
    revision = Column(Integer, nullable=False)
    payload = Column(JSONField, nullable=False)
    __table_args__ = (
        UniqueConstraint('owner_id', 'preparation_id', 'seed_trial_id', name='teaching_workbench_source_unique'),
    )


class TeachingComparison(Base):
    __tablename__ = 'teaching_comparison'
    id = Column(Text, primary_key=True)
    owner_id = Column(Text, nullable=False)
    workbench_id = Column(Text, nullable=False)
    request_key = Column(Text, nullable=False)
    request_hash = Column(Text, nullable=False)
    payload = Column(JSONField, nullable=False)
    trial_ids = Column(JSONField, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    __table_args__ = (UniqueConstraint('workbench_id', 'request_key', name='teaching_comparison_request_unique'),)


class SavedTeachingPlan(Base):
    __tablename__ = 'saved_teaching_plan'
    id = Column(Text, primary_key=True)
    owner_id = Column(Text, nullable=False)
    trial_id = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    config = Column(JSONField, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    __table_args__ = (UniqueConstraint('owner_id', 'trial_id', name='saved_teaching_plan_source_unique'),)


class TeachingPlanAdoption(Base):
    __tablename__ = 'teaching_plan_adoption'
    id = Column(Text, primary_key=True)
    preparation_id = Column(Text, nullable=False)
    request_key = Column(Text, nullable=False)
    request_hash = Column(Text, nullable=False)
    result = Column(JSONField, nullable=False)
    __table_args__ = (UniqueConstraint('preparation_id', 'request_key', name='teaching_plan_adoption_request_unique'),)
