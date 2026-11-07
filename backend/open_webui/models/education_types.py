"""Versioned teaching configuration and explicit teacher assignment permissions."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, Integer, Text, UniqueConstraint

from open_webui.internal.db import Base, JSONField
from open_webui.models.education import ReflectionQuestion, RubricSchema, validate_reflection_questions
from open_webui.services.education.task_types import TaskMode


class TeacherTaskAccess(Base):
    __tablename__ = 'teacher_task_access'
    __table_args__ = (
        CheckConstraint(
            '(default_task_mode IS NULL AND NOT from_scratch AND NOT revise_draft AND NOT revise_argument) OR '
            "(default_task_mode IS NOT NULL AND default_task_mode = 'from_scratch' AND from_scratch) OR "
            "(default_task_mode IS NOT NULL AND default_task_mode = 'revise_draft' AND revise_draft) OR "
            "(default_task_mode IS NOT NULL AND default_task_mode = 'revise_argument' AND revise_argument)",
            name='teacher_task_default_check',
        ),
    )
    user_id = Column(Text, primary_key=True)
    from_scratch = Column(Boolean, nullable=False, default=True)
    revise_draft = Column(Boolean, nullable=False, default=False)
    revise_argument = Column(Boolean, nullable=False, default=False)
    default_task_mode = Column(Text, nullable=True)


class TeacherTaskAccessForm(BaseModel):
    model_config = ConfigDict(extra='forbid')
    allowed_task_modes: list[TaskMode] = Field(max_length=3)
    default_task_mode: TaskMode | None

    @model_validator(mode='after')
    def validate_default(self):
        if len(set(self.allowed_task_modes)) != len(self.allowed_task_modes):
            raise ValueError('Assignment types must be unique')
        if self.allowed_task_modes:
            if self.default_task_mode not in self.allowed_task_modes:
                raise ValueError('Default assignment type must be authorized')
        elif self.default_task_mode is not None:
            raise ValueError('An account with no assignment types has no default')
        return self


class TeachingConfiguration(Base):
    __tablename__ = 'teaching_configuration'
    __table_args__ = (
        CheckConstraint("task_mode IN ('from_scratch', 'revise_draft', 'revise_argument')", name='teaching_type_check'),
        CheckConstraint('version > 0', name='teaching_version_check'),
    )
    task_mode = Column(Text, primary_key=True)
    version = Column(Integer, primary_key=True)
    payload = Column(JSONField, nullable=False)
    created_at = Column(BigInteger, nullable=False)


class TeachingConfigForm(BaseModel):
    model_config = ConfigDict(extra='forbid')
    standards: str = Field(min_length=1, max_length=30000)
    prompt: str = Field(min_length=1, max_length=30000)
    default_description: str = Field(max_length=30000)
    scoring_mode: Literal['dimensions', 'total']
    score_max: int = Field(gt=0, le=10000)
    rubric_schema: RubricSchema
    reflection_questions: list[ReflectionQuestion] = Field(max_length=20)

    @model_validator(mode='after')
    def validate_config(self):
        validate_reflection_questions(self.reflection_questions)
        if self.scoring_mode == 'total':
            if self.rubric_schema.criteria:
                raise ValueError('Total-only scoring has no rubric criteria')
        elif not self.rubric_schema.criteria or self.rubric_schema.total_score != self.score_max:
            raise ValueError('Rubric maximum scores must add up to assignment maximum score')
        return self


class TeachingConfigSnapshot(TeachingConfigForm):
    task_mode: TaskMode
    version: int = Field(gt=0)
    created_at: int


class TeachingConfigUpdate(TeachingConfigForm):
    expected_version: int = Field(gt=0)


class RevisionReading(Base):
    __tablename__ = 'revision_reading'
    __table_args__ = (
        UniqueConstraint('writing_session_id', 'purpose', 'source_hash', name='reading_request_unique'),
        CheckConstraint("purpose IN ('first_read', 'revision_review', 'whole_review')", name='reading_purpose_check'),
        CheckConstraint("status IN ('running', 'ready', 'failed')", name='reading_status_check'),
    )
    id = Column(Text, primary_key=True)
    writing_session_id = Column(Text, nullable=False, index=True)
    sequence_no = Column(Integer, nullable=False)
    purpose = Column(Text, nullable=False)
    source_hash = Column(Text, nullable=False)
    source_version_id = Column(Text, nullable=True)
    source_text = Column(Text, nullable=False)
    context = Column(JSONField, nullable=False)
    status = Column(Text, nullable=False)
    feedback = Column(JSONField, nullable=True)
    model_id = Column(Text, nullable=True)
    thinking = Column(Text, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    completed_at = Column(BigInteger, nullable=True)
