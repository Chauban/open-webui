"""Private preparations and immutable teaching execution evidence."""

from typing import Literal

from open_webui.internal.db import Base, JSONField
from open_webui.models.education import AssignmentCreateForm, ThinkingSetting
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import BigInteger, CheckConstraint, Column, Integer, Text, UniqueConstraint


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class TeachingTextFeedback(StrictModel):
    """Internal reading envelope, built by the server rather than generated as JSON."""

    understanding: Literal[''] = ''
    strength: None = None
    focus: list[dict[str, str]] = Field(default_factory=list, max_length=0)
    overview: str = Field(min_length=1)

    @model_validator(mode='after')
    def visible_reply(self):
        if not self.overview.strip():
            raise ValueError('Teaching model returned no visible reply')
        return self


class AiCandidate(StrictModel):
    prompt: str = Field(min_length=1, max_length=65000)
    model_id: str = Field(min_length=1, max_length=256)
    thinking: ThinkingSetting = 'model_default'
    template_version: int = Field(gt=0)

    @model_validator(mode='after')
    def nonempty_prompt(self):
        if not self.prompt.strip():
            raise ValueError('Teaching prompt is required')
        return self


class PreparationPayload(StrictModel):
    # The normal form permits missing classroom/deadline; publication validates them.
    assignment: AssignmentCreateForm
    ai: AiCandidate

    @model_validator(mode='after')
    def argument_only(self):
        if self.assignment.task_mode != 'revise_argument':
            raise ValueError('Teaching trials currently support argument revision only')
        return self


class PreparationCreate(StrictModel):
    assignment_id: str | None = None
    payload: PreparationPayload


class PreparationUpdate(StrictModel):
    expected_revision: int = Field(gt=0)
    payload: PreparationPayload


class PublishPreparation(StrictModel):
    expected_revision: int = Field(gt=0)
    expected_config_revision: int | None = Field(default=None, gt=0)
    idempotency_key: str = Field(min_length=8, max_length=128)
    change_summary: str = Field(default='', max_length=1000)


class TrialCreate(StrictModel):
    preparation_id: str
    expected_revision: int = Field(gt=0)
    source_trial_id: str | None = None
    source_sequence: int | None = Field(default=None, ge=0)
    reuse_sample_from_trial_id: str | None = None

    @model_validator(mode='after')
    def one_source(self):
        if self.source_trial_id and (self.source_sequence is None or self.reuse_sample_from_trial_id):
            raise ValueError('Choose either a completed node or a sample')
        return self


class TrialAction(StrictModel):
    expected_sequence: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128)
    action: Literal[
        'confirm',
        'first_read',
        'save',
        'coaching_chat',
        'stop',
        'retry',
    ]
    text: str = Field(default='', max_length=200000)


class AdoptTrial(StrictModel):
    expected_revision: int = Field(gt=0)
    trial_id: str


class AdoptRevision(StrictModel):
    expected_revision: int = Field(gt=0)
    revision_id: str


class TeachingModelPolicy(StrictModel):
    model_ids: list[str] = Field(default_factory=list, max_length=100)
    recommended_model_id: str | None = None

    @model_validator(mode='after')
    def valid_recommendation(self):
        if len(set(self.model_ids)) != len(self.model_ids):
            raise ValueError('Teaching models must be unique')
        if self.recommended_model_id and self.recommended_model_id not in self.model_ids:
            raise ValueError('Recommended model must be authorized')
        return self


class ModelRoute(StrictModel):
    base_model_id: str
    url_index: int | None
    connection_hash: str | None = None


class ModelBinding(StrictModel):
    model_id: str
    base_model_id: str
    workspace_model: bool
    route: ModelRoute
    params: dict[str, int | float | str | list[str]]
    filter_fingerprint: str
    thinking_support: dict[str, bool]
    thinking_format: str | None
    capabilities: dict[str, bool]


class AiRuntimeConfig(StrictModel):
    ai: AiCandidate
    binding: ModelBinding
    title: str
    description: str
    description_version: int = Field(gt=0)
    execution_version: str
    validation_environment: str
    ai_revision_id: str | None = None
    ai_revision: int | None = Field(default=None, gt=0)
    change_summary: str = ''


class FrozenAiRevision(StrictModel):
    id: str
    revision: int = Field(gt=0)
    config: AiRuntimeConfig
    change_summary: str
    created_at: int


class FrozenTeachingCall(StrictModel):
    id: str
    revision_id: str
    status: Literal['ready']
    sequence: int = Field(gt=0)
    context: dict
    created_at: int
    completed_at: int


class FrozenTeachingEvidence(StrictModel):
    schema_version: Literal['2026-11-07.1'] = '2026-11-07.1'
    revisions: list[FrozenAiRevision]
    calls: list[FrozenTeachingCall]


class TeachingPreparation(Base):
    __tablename__ = 'teaching_preparation'
    id = Column(Text, primary_key=True)
    owner_id = Column(Text, nullable=False, index=True)
    assignment_id = Column(Text, nullable=True)
    base_config_revision = Column(Integer, nullable=True)
    revision = Column(Integer, nullable=False)
    payload = Column(JSONField, nullable=False)
    adopted_binding = Column(JSONField, nullable=True)
    published = Column(JSONField, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    __table_args__ = (CheckConstraint('revision > 0', name='teaching_preparation_revision_positive'),)


class AssignmentAiRevision(Base):
    __tablename__ = 'assignment_ai_revision'
    id = Column(Text, primary_key=True)
    assignment_id = Column(Text, nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    config = Column(JSONField, nullable=False)
    author_id = Column(Text, nullable=False)
    change_summary = Column(Text, nullable=False)
    preparation_id = Column(Text, nullable=False)
    evidence = Column(JSONField, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    __table_args__ = (
        UniqueConstraint('assignment_id', 'revision', name='assignment_ai_revision_unique'),
        CheckConstraint('revision > 0', name='assignment_ai_revision_positive'),
    )


class TeachingTrialSession(Base):
    __tablename__ = 'teaching_trial_session'
    id = Column(Text, primary_key=True)
    owner_id = Column(Text, nullable=False, index=True)
    preparation_id = Column(Text, nullable=False, index=True)
    config = Column(JSONField, nullable=False)
    fingerprint = Column(Text, nullable=False)
    source_trial_id = Column(Text, nullable=True)
    source_sequence = Column(Integer, nullable=True)
    sequence = Column(Integer, nullable=False)
    state = Column(JSONField, nullable=False)
    created_at = Column(BigInteger, nullable=False)


class TeachingTrialEvent(Base):
    __tablename__ = 'teaching_trial_event'
    id = Column(Text, primary_key=True)
    trial_id = Column(Text, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    idempotency_key = Column(Text, nullable=False)
    request_hash = Column(Text, nullable=False)
    action = Column(Text, nullable=False)
    state = Column(JSONField, nullable=False)
    call = Column(JSONField, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    __table_args__ = (
        UniqueConstraint('trial_id', 'sequence', name='trial_event_sequence_unique'),
        UniqueConstraint('trial_id', 'idempotency_key', name='trial_event_request_unique'),
    )


class TeachingCall(Base):
    __tablename__ = 'teaching_call'
    id = Column(Text, primary_key=True)
    session_id = Column(Text, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    assignment_id = Column(Text, nullable=False)
    revision_id = Column(Text, nullable=False)
    request_key = Column(Text, nullable=False)
    status = Column(Text, nullable=False)
    context = Column(JSONField, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    completed_at = Column(BigInteger, nullable=True)
    __table_args__ = (
        UniqueConstraint('session_id', 'request_key', name='teaching_call_request_unique'),
        UniqueConstraint('session_id', 'sequence', name='teaching_call_sequence_unique'),
        CheckConstraint("status IN ('running', 'ready', 'failed', 'stopped')", name='teaching_call_status_check'),
    )
