"""Operational metadata only: never store prompts, responses, URLs or credentials."""

from open_webui.internal.db import Base
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, ForeignKey, Index, Integer, Text


class ModelCall(Base):
    __tablename__ = 'model_call'

    id = Column(Text, primary_key=True)
    model_id = Column(Text, nullable=False)
    user_id = Column(Text, nullable=True)
    started_at = Column(BigInteger, nullable=False)
    duration_ms = Column(Integer, nullable=False)
    outcome = Column(Text, nullable=False)
    fallback_used = Column(Boolean, nullable=False)
    __table_args__ = (
        CheckConstraint("outcome IN ('success','failed','cancelled')", name='model_call_outcome'),
        Index('ix_model_call_started_model', 'started_at', 'model_id'),
    )


class ModelCallAttempt(Base):
    __tablename__ = 'model_call_attempt'

    id = Column(Text, primary_key=True)
    call_id = Column(Text, ForeignKey('model_call.id', ondelete='CASCADE'), nullable=False)
    model_id = Column(Text, nullable=False)
    route = Column(Text, nullable=False)
    started_at = Column(BigInteger, nullable=False)
    duration_ms = Column(Integer, nullable=False)
    outcome = Column(Text, nullable=False)
    reason = Column(Text, nullable=True)
    http_status = Column(Integer, nullable=True)
    fallback = Column(Boolean, nullable=False)
    __table_args__ = (
        CheckConstraint("outcome IN ('success','failed','cancelled')", name='model_attempt_outcome'),
        Index('ix_model_call_attempt_call', 'call_id'),
        Index('ix_model_call_attempt_started', 'started_at'),
    )
