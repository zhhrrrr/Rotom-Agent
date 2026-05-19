import logging
import sys


LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def setup_logging() -> None:
    """配置项目基础日志。

    Docker 会收集 stdout/stderr，所以这里把日志输出到标准输出。
    force=True 可以覆盖 uvicorn/脚本启动时已有的默认配置，保证格式统一。
    """

    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        stream=sys.stdout,
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
