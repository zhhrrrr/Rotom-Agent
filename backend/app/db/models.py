from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# SQLAlchemy ORM 的所有模型都要继承同一个 Base。
# Base.metadata 会收集下面所有表结构，database.py 里的 create_all 就是读取这里的 metadata 来建表。
class Base(DeclarativeBase):
    pass


def new_id(prefix: str) -> str:
    # 统一生成带业务前缀的主键，例如 sess_xxx、run_xxx。
    return f"{prefix}_{uuid4().hex}"


DEFAULT_USER_ID = "user_default"
DEFAULT_WORKSPACE_ID = "workspace_default"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: new_id("user"),
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    workspaces: Mapped[list[Workspace]] = relationship(back_populates="user")
    sessions: Mapped[list[Session]] = relationship(back_populates="user")
    runs: Mapped[list[Run]] = relationship(back_populates="user")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: new_id("workspace"),
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    root_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="workspaces")
    sessions: Mapped[list[Session]] = relationship(back_populates="workspace")
    runs: Mapped[list[Run]] = relationship(back_populates="workspace")


# 一个 Python 类对应一张数据库表。
# __tablename__ 指定真实表名，所以这个类会创建 public.sessions 表。
class Session(Base):
    __tablename__ = "sessions"

    # 字段定义语法：
    # 字段名: Mapped[Python类型] = mapped_column(数据库类型, 约束...)
    #
    # primary_key=True 表示主键。
    # default=lambda: new_id("sess") 表示插入数据时如果没传 id，就自动生成。
    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: new_id("sess"),
    )
    # nullable=False 表示数据库层面不允许为空。
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
        default=DEFAULT_USER_ID,
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        index=True,
        nullable=False,
        default=DEFAULT_WORKSPACE_ID,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # server_default=func.now() 表示由 PostgreSQL 在插入时填充当前时间。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # onupdate=func.now() 表示 ORM 更新这行数据时同步刷新更新时间。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # relationship 不会单独创建字段，它描述 ORM 对象之间怎么互相访问。
    # Session.messages 表示可以从一个 Session 对象拿到它下面的多条 Message。
    # back_populates 要和 Message.session 对应。
    user: Mapped[User] = relationship(back_populates="sessions")
    workspace: Mapped[Workspace] = relationship(back_populates="sessions")
    messages: Mapped[list[Message]] = relationship(back_populates="session")
    runs: Mapped[list[Run]] = relationship(back_populates="session")


# messages 表保存用户、模型、工具等消息。
class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: new_id("msg"),
    )
    # ForeignKey("sessions.id") 表示这个字段引用 sessions 表的 id 字段。
    # index=True 会为该字段建索引，方便按 session_id 查询历史消息。
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
        default=DEFAULT_USER_ID,
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        index=True,
        nullable=False,
        default=DEFAULT_WORKSPACE_ID,
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id"),
        index=True,
        nullable=False,
    )
    # run_id 可以为空，因为有些历史消息可能不属于某一次 Run。
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.id"),
        index=True,
        nullable=True,
    )
    # role 后续会存 user / assistant / tool / system。
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    # Text 适合存较长文本，例如用户输入、模型回答、工具输出摘要。
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    session: Mapped[Session] = relationship(back_populates="messages")
    run: Mapped[Run | None] = relationship(back_populates="messages")


# runs 表表示一次 Agent 执行任务。
class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: new_id("run"),
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
        default=DEFAULT_USER_ID,
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        index=True,
        nullable=False,
        default=DEFAULT_WORKSPACE_ID,
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id"),
        index=True,
        nullable=False,
    )
    user_input: Mapped[str] = mapped_column(Text, nullable=False)
    # status 会存 queued / running / completed / failed / cancelled。
    # index=True 方便后续查 queued 或 running 的任务。
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    current_step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    # error 可为空；只有失败时记录错误信息。
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user: Mapped[User] = relationship(back_populates="runs")
    workspace: Mapped[Workspace] = relationship(back_populates="runs")
    session: Mapped[Session] = relationship(back_populates="runs")
    messages: Mapped[list[Message]] = relationship(back_populates="run")
    tool_calls: Mapped[list[ToolCall]] = relationship(back_populates="run")
    model_calls: Mapped[list[ModelCall]] = relationship(back_populates="run")
    event_logs: Mapped[list[EventLog]] = relationship(back_populates="run")
    chunks: Mapped[list[RunChunk]] = relationship(back_populates="run")


# tool_calls 表记录模型要求调用了什么工具、传了什么参数、工具返回了什么结果。
class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: new_id("tool"),
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
        default=DEFAULT_USER_ID,
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        index=True,
        nullable=False,
        default=DEFAULT_WORKSPACE_ID,
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id"),
        index=True,
        nullable=False,
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # JSONB 是 PostgreSQL 的 JSON 类型，适合保存结构化参数。
    # tool_args 例如 {"path": "README.md"}。
    tool_args: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # tool_result 可为空，因为工具执行前或失败时可能还没有结果。
    tool_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    runtime_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    run: Mapped[Run] = relationship(back_populates="tool_calls")


class ModelCall(Base):
    __tablename__ = "model_calls"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: new_id("modelcall"),
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        index=True,
        nullable=False,
    )
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    request_messages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    request_tools: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    response_message: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    run: Mapped[Run] = relationship(back_populates="model_calls")


class EventLog(Base):
    __tablename__ = "event_logs"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: new_id("evt"),
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        index=True,
        nullable=False,
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("sessions.id"),
        index=True,
        nullable=True,
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"), index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    run: Mapped[Run | None] = relationship(back_populates="event_logs")


class RunChunk(Base):
    __tablename__ = "run_chunks"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "chunk_index",
            name="uq_run_chunks_run_id_chunk_index",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: new_id("chunk"),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        index=True,
        nullable=False,
    )
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 结构化 JSON
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_final: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    run: Mapped[Run] = relationship(back_populates="chunks")
