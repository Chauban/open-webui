"""Immutable, confirmed import evidence, separate from editable student prose."""

from typing import Annotated, Literal

from open_webui.internal.db import Base, JSONField
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, Text


class WritingMaterial(Base):
    __tablename__ = 'writing_material'

    id = Column(Text, primary_key=True)
    writing_session_id = Column(Text, ForeignKey('writing_session.id', ondelete='CASCADE'), nullable=False, index=True)
    filename = Column(Text, nullable=False)
    bundle_path = Column(Text, nullable=False)
    data = Column(JSONField, nullable=False)
    active = Column(Boolean, nullable=False, default=False)
    confirmed_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)


class MaterialBlock(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str
    kind: Literal['image', 'page', 'footnote', 'endnote', 'textbox', 'header', 'footer', 'annotation', 'unsupported']
    location: str
    text: str = Field(default='', max_length=200_000)
    extracted_text: str = Field(default='', max_length=200_000)
    native_text: str = Field(default='', max_length=200_000)
    status: Literal['read', 'unreadable', 'corrected', 'disabled']
    detail: str = ''
    image: bool = False


class MaterialSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str
    corrections: dict[str, Annotated[str, Field(max_length=200_000)]] = Field(default_factory=dict, max_length=200)


class MaterialAttachForm(BaseModel):
    model_config = ConfigDict(extra='forbid')

    materials: list[MaterialSelection] = Field(max_length=20)
    replace: bool = False
