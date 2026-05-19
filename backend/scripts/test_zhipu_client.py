import asyncio
import sys
from pathlib import Path


# 这个脚本在 backend/scripts 目录下。
# 直接 python scripts/test_zhipu_client.py 时，Python 默认只把 scripts 加进 import path。
# 手动把 backend 根目录加进去，才能导入 app.agent。
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(BACKEND_ROOT))

from app.agent import ZhipuModelClient


async def main() -> None:
    client = ZhipuModelClient()
    response = await client.chat(
        messages=[
            {"role": "system", "content": "你是一个回答简洁的中文助手。"},
            {"role": "user", "content": "请用一句话回答：Rotom Agent 是什么？"},
        ]
    )

    # Chat Completions 的文本通常在 choices[0].message.content。
    print(response.choices[0].message.content)


if __name__ == "__main__":
    asyncio.run(main())
