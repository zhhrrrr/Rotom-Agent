import shlex
import subprocess
from pathlib import Path
from typing import Any

from app.core.config import settings


COMMAND_TIMEOUT_SECONDS = 20
MAX_STDOUT_CHARS = 8_000
MAX_STDERR_CHARS = 8_000

# 黑名单是第二道保险。
# 注意：真正的主策略是下面的白名单；黑名单只是让危险命令更早、更明确地报错。
# 比如 python 本身很强大，可以执行任意代码，所以只允许 python --version 这种特例。
DANGEROUS_COMMANDS = {
    "chmod",      # 修改文件/目录权限。危险点：可能把敏感文件改成任何人可读/可写，或让脚本变成可执行文件。
    "chown",      # 修改文件/目录所有者。危险点：可能改变系统文件或项目文件的归属，造成权限混乱。
    "curl",       # 发起 HTTP/HTTPS 请求、下载内容。危险点：可能下载恶意脚本，也可能把本地敏感信息上传出去。
    "dd",         # 低级磁盘读写工具。危险点：可以直接覆盖磁盘、分区、镜像文件，误用会毁坏系统或数据。
    "docker",     # 管理 Docker 容器、镜像、网络、卷。危险点：可能启动高权限容器、删除数据卷、访问宿主机资源。
    "git",        # Git 版本控制工具。危险点：可能拉取外部代码、覆盖本地修改、泄露远程仓库地址或提交敏感文件。
    "kill",       # 终止进程。危险点：可能杀掉数据库、Web 服务、系统关键进程，导致服务中断。
    "mkfs",       # 格式化文件系统。危险点：会清空磁盘/分区数据，属于极高危命令。
    "mv",         # 移动或重命名文件/目录。危险点：可能覆盖文件、移动系统文件、破坏项目目录结构。
    "nc",         # netcat 网络工具，可建立 TCP/UDP 连接。危险点：常被用于端口扫描、反弹 shell、数据外传。
    "pip",        # Python 包管理工具。危险点：可能安装不可信依赖，依赖安装脚本可执行任意代码。
    "python",     # Python 解释器。危险点：可以执行任意 Python 代码，读写文件、访问网络、执行系统命令。
    "reboot",     # 重启系统。危险点：会中断当前所有服务和任务。
    "rm",         # 删除文件/目录。危险点：rm -rf 可递归删除大量文件，误用会删掉项目甚至系统文件。
    "scp",        # 通过 SSH 复制文件。危险点：可能把本地文件传到远程，也可能从远程拉取不可信文件。
    "shutdown",   # 关闭系统。危险点：会直接关机，导致服务中断。
    "ssh",        # 远程登录命令。危险点：可以连接外部主机，执行远程命令，也可能造成数据外传。
    "sudo",       # 以管理员/root 权限执行命令。危险点：会绕过普通用户权限限制，影响整个系统。
    "wget",       # 下载文件。危险点：可能下载恶意脚本、二进制文件，配合 sh/python 执行会很危险。
}

# 这些是 shell 语法符号，不是普通命令参数。
# 因为 run_shell 不使用 shell=True，理论上它们不会被 shell 解释；
# 但这里仍然拦截，是为了避免模型传入类似 "python --version && rm -rf /" 的组合命令。
DANGEROUS_TOKENS = {
    ";",    # 命令分隔符。可以在一行里连续执行多个命令，例如：ls; rm -rf logs
    "&&",   # 逻辑与。前一个命令成功后才执行后一个命令，例如：mkdir test && rm -rf test
    "||",   # 逻辑或。前一个命令失败后执行后一个命令，例如：cat a.txt || rm -rf logs
    "|",    # 管道符。把前一个命令的输出传给后一个命令，例如：cat file | sh
    ">",    # 输出重定向。把命令输出写入文件，会覆盖原文件，例如：echo x > config.py
    ">>",   # 追加重定向。把命令输出追加到文件末尾，例如：echo x >> ~/.ssh/authorized_keys
    "<",    # 输入重定向。从文件读取内容作为命令输入，例如：python < script.py
    "`",    # 反引号命令替换。会执行里面的命令，例如：echo `whoami`
    "$(",   # 子命令替换。会执行括号里的命令，例如：echo $(whoami)
}


def _workspace_root(workspace_root: str | None = None) -> Path:
    # 命令执行目录固定在 WORKSPACE_ROOT。
    # 这样 pwd/ls/cat 默认都围绕工作区运行，而不是围绕项目代码目录或系统目录运行。
    if workspace_root is not None:
        return Path(workspace_root).resolve()
    return settings.workspace_root.resolve()


def _resolve_workspace_path(path: str, workspace_root: str | None = None) -> Path:
    # cat/ls 带路径参数时，也必须限制在 WORKSPACE_ROOT 内。
    # 这和 file_tools.py 的路径安全逻辑是一致的。
    root = _workspace_root(workspace_root)
    raw_path = Path(path)

    # 绝对路径例如 /etc/passwd 不允许。
    # 工具只能处理工作区相对路径。
    if raw_path.is_absolute():
        raise ValueError("Path must be relative to WORKSPACE_ROOT")

    # resolve() 会规整 .. 和符号链接。
    # 例如 workspace/a/../b 会变成 workspace/b。
    target = (root / raw_path).resolve()
    try:
        # relative_to(root) 用来证明 target 没有逃出工作区。
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("Path escapes WORKSPACE_ROOT") from exc

    return target


def _truncate(text: str, limit: int) -> str:
    # 命令输出可能很长，比如 cat 一个大文件或 ls 很多内容。
    # 截断可以保护数据库、日志和模型上下文不被撑爆。
    if len(text) <= limit:
        return text

    return text[:limit] + "\n...[truncated]"


def _validate_no_shell_syntax(parts: list[str]) -> None:
    # shlex.split 后，"python --version && rm -rf /" 会变成多个 token。
    # 这里逐个检查，发现 shell 组合语法就拒绝。
    for part in parts:
        if part in DANGEROUS_TOKENS:
            raise ValueError(f"Dangerous shell token is not allowed: {part}")
        if any(token in part for token in DANGEROUS_TOKENS):
            raise ValueError(f"Dangerous shell syntax is not allowed: {part}")


def _build_allowed_command(command: str, workspace_root: str | None = None) -> list[str]:
    # shlex.split 负责把命令字符串拆成参数列表。
    # 例如 "python --version" -> ["python", "--version"]。
    # 后面 subprocess.run 会直接接收 list，不通过 shell 执行。
    parts = shlex.split(command)
    if not parts:
        raise ValueError("Command cannot be empty")

    _validate_no_shell_syntax(parts)

    # 第一个参数是命令名，例如 ls/cat/python。
    command_name = parts[0]

    # python/pip 本身风险较高，所以这里只允许 --version。
    # 不允许 python -c、python script.py、pip install 等形式。
    if parts in (["python", "--version"], ["python3", "--version"]):
        return parts
    if parts in (["pip", "--version"], ["pip3", "--version"]):
        return parts

    # 如果命令名在危险黑名单里，直接拒绝。
    # 例如 rm、curl、ssh、docker 都不该在第一版给模型开放。
    if command_name in DANGEROUS_COMMANDS:
        raise ValueError(f"Dangerous command is not allowed: {command_name}")

    # pwd 是只读查询命令，没有参数，允许。
    if parts == ["pwd"]:
        return parts

    if command_name == "ls":
        # 第一版只允许 ls、ls .、ls <workspace-relative-path>。
        # 不开放 -la 等 flags，避免后续参数语义慢慢变复杂。
        if len(parts) > 2:
            raise ValueError("ls only supports zero or one path argument")
        if len(parts) == 2:
            # 如果 ls 带路径，也必须是工作区内的相对路径。
            _resolve_workspace_path(parts[1], workspace_root)
        return parts

    if command_name == "cat":
        # cat 只允许读取一个工作区内文件。
        # 不允许 cat a b，也不允许 cat /etc/passwd。
        if len(parts) != 2:
            raise ValueError("cat only supports exactly one file path")

        target = _resolve_workspace_path(parts[1], workspace_root)
        if not target.is_file():
            raise ValueError(f"Not a file: {parts[1]}")
        return parts

    raise ValueError(f"Command is not allowed: {command_name}")


def run_shell(command: str, workspace_root: str | None = None) -> dict[str, Any]:
    """执行低风险白名单命令。

    第一版不是开放任意 shell，而是只允许少量只读/查询类命令。
    """

    parts = _build_allowed_command(command, workspace_root)

    try:
        # 重点：这里没有 shell=True。
        # subprocess.run(["python", "--version"]) 会直接执行 python 程序，
        # 不会让 /bin/sh 解释 &&、|、> 这类 shell 语法。
        completed = subprocess.run(
            parts,
            # cwd 固定为工作区根目录。
            # 所以 pwd 返回 WORKSPACE_ROOT，ls/cat 默认也从工作区看。
            cwd=_workspace_root(workspace_root),
            capture_output=True,
            # text=True 表示 stdout/stderr 返回 str，而不是 bytes。
            text=True,
            # 防止命令卡死，例如某些命令一直等待输入。
            timeout=COMMAND_TIMEOUT_SECONDS,
            # check=False 表示即使命令 exit_code 非 0，也不抛异常。
            # 我们把 exit_code/stdout/stderr 作为工具结果返回给模型。
            check=False,
        )
        return {
            "command": command,
            "exit_code": completed.returncode,
            "stdout": _truncate(completed.stdout, MAX_STDOUT_CHARS),
            "stderr": _truncate(completed.stderr, MAX_STDERR_CHARS),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        # 超时也返回结构化结果，而不是让整个 Agent 崩掉。
        # ToolBroker 会把这个结果写入 tool_calls。
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return {
            "command": command,
            "exit_code": None,
            "stdout": _truncate(stdout, MAX_STDOUT_CHARS),
            "stderr": _truncate(stderr, MAX_STDERR_CHARS),
            "timed_out": True,
        }
