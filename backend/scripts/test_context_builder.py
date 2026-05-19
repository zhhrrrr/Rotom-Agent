import asyncio
import json
import sys
from pathlib import Path


# 这个脚本在 backend/scripts 下。
# 直接运行脚本时，需要把 backend 根目录放进 import path，才能导入 app 包。
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(BACKEND_ROOT))

from app.agent import ContextBuilder
from app.db.database import AsyncSessionLocal


async def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/test_context_builder.py <session_id>")

    session_id = sys.argv[1]

    async with AsyncSessionLocal() as db:
        builder = ContextBuilder(db)
        messages = await builder.build(session_id)

    # ensure_ascii=False 让中文正常显示，不转成 \u4f60\u597d。
    print(json.dumps(messages, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
