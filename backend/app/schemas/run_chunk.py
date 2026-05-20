from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# 限制 chunk_type 的可选值
# 表示 Agent Runtime 中支持的事件类型
RunChunkType = Literal[
    "message_delta",   # 流式文本增量
    "message_final",   # 最终完整消息
    "tool_started",    # 工具开始执行
    "tool_delta",      # 工具流式输出
    "tool_finished",   # 工具执行完成
    "status",          # 状态更新
    "error",           # 错误事件
]


# 创建 RunChunk 时使用的数据模型
class RunChunkCreate(BaseModel):
    run_id: str              # 当前 chunk 属于哪个 run
    user_id: str             # 用户 ID
    workspace_id: str        # 工作区 ID
    session_id: str          # 会话 ID

    # chunk 类型
    chunk_type: RunChunkType

    # 给用户展示的文本内容
    content: str = ""

    # 消息角色（assistant/tool/system/user）
    role: str | None = Field(default=None, max_length=32)

    # 结构化运行时数据
    # 例如 tool 参数、tool result、metadata 等
    payload: dict[str, Any] | None = None

    # 是否为最终 chunk
    is_final: bool = False


# 从数据库读取 RunChunk 时返回的数据模型
class RunChunkRead(BaseModel):
    id: str                  # chunk 主键 ID

    run_id: str              # 所属 run
    user_id: str             # 用户 ID
    workspace_id: str        # 工作区 ID
    session_id: str          # 会话 ID

    # 当前 chunk 在 run 中的顺序
    chunk_index: int

    # chunk 类型
    chunk_type: RunChunkType

    # 消息角色
    role: str | None

    # 展示给用户的内容
    content: str

    # 结构化 runtime 数据
    payload: dict[str, Any] | None

    # 是否为最终 chunk
    is_final: bool

    # chunk 创建时间
    created_at: datetime