from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    success: bool
    data: Any | None = None
    error: str | None = None
    display: str | None = None

    def to_model_message(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
        }
