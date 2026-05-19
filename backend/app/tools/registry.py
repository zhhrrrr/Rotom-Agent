from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from app.tools.file_tools import list_dir, read_file, write_file
from app.tools.shell_tools import run_shell


@dataclass(frozen=True)
class ToolSpec:
    """单个工具的描述。

    这里先只保存模型需要知道的信息：
    - name: 工具名
    - description: 工具用途
    - parameters: 工具参数的 JSON Schema
    - risk_level: low / medium / high
    - runtime_type: local / docker
    - enabled: 是否开放给模型和 Broker
    """

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    risk_level: str
    runtime_type: str
    enabled: bool = True

    def to_openai_tool(self) -> dict[str, Any]:
        # OpenAI-compatible tools schema 固定是这个外层结构。
        # 智谱 GLM 兼容 OpenAI Chat Completions，所以也使用这个格式。
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """工具注册表。

    Agent 不应该到处散落工具定义。
    Registry 统一负责注册、查找，并把工具转换成模型能识别的 schema。
    """

    def __init__(self) -> None:
        # key 是工具名，value 是 ToolSpec。
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> ToolSpec:
        # 注册工具时要求名字唯一，避免两个工具同名导致模型调用时无法判断。
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")

        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> ToolSpec | None:
        # 找不到时返回 None，调用方可以自己决定是报错还是忽略。
        return self._tools.get(name)

    def openai_tools(self) -> list[dict[str, Any]]:
        # 把内部 ToolSpec 列表转成模型 API 需要的 tools 参数。
        # disabled 工具不暴露给模型，避免模型主动选择它。
        return [tool.to_openai_tool() for tool in self._tools.values() if tool.enabled]


tool_registry = ToolRegistry()


tool_registry.register(
    ToolSpec(
        name="list_dir",
        description="列出工作区中指定目录下的文件和子目录。",
        handler=list_dir,
        risk_level="low",
        runtime_type="local",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要列出的目录路径，相对于当前工作区根目录。",
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    )
)


tool_registry.register(
    ToolSpec(
        name="read_file",
        description="读取工作区中的文本文件内容。",
        handler=read_file,
        risk_level="low",
        runtime_type="local",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要读取的文件路径，相对于当前工作区根目录。",
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    )
)


tool_registry.register(
    ToolSpec(
        name="write_file",
        description="向工作区内写入文本文件。风险等级 medium。会自动创建父目录。",
        handler=write_file,
        risk_level="medium",
        runtime_type="local",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要写入的文件路径，相对于当前工作区根目录。",
                },
                "content": {
                    "type": "string",
                    "description": "要写入文件的 UTF-8 文本内容。",
                },
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    )
)


tool_registry.register(
    ToolSpec(
        name="run_shell",
        description=(
            "执行低风险白名单命令。第一版只允许 pwd、ls、cat、"
            "python --version、pip --version。风险等级 high，必须经过 DockerRuntime 策略。"
        ),
        handler=run_shell,
        risk_level="high",
        runtime_type="docker",
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的低风险命令，例如 python --version。",
                }
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    )
)
