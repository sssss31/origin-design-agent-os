"""Conversations and messages (spec §7). A conversation may involve many agents."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_project_id_last_message_at", "project_id", "last_message_at"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="New chat")
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False, comment="active | archived"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        comment="agent that plain messages go to after a /command activated it",
    )

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, comment="user | assistant | system")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    command: Mapped[str | None] = mapped_column(
        String(41), nullable=True, comment="explicit slash command, kept visible"
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    agent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agent_versions.id", ondelete="SET NULL"), nullable=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, comment="workflow run that produced/was triggered by this message"
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    attachments: Mapped[list[MessageAttachment]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class MessageAttachment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "message_attachments"

    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("assets.id", ondelete="CASCADE"), nullable=True
    )
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=True
    )

    message: Mapped[Message] = relationship(back_populates="attachments")


class AgentSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-conversation, per-agent model context: the transcript the provider saw last time.

    This is what makes `/copy` "remember" — the next turn with the same agent in the same
    conversation continues from these items (trimmed to the model's context window).
    """

    __tablename__ = "agent_sessions"
    __table_args__ = (UniqueConstraint("conversation_id", "agent_id"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_type: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    input_list: Mapped[list] = mapped_column(
        JSONB, default=list, nullable=False, comment="provider transcript items"
    )
    turns: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
