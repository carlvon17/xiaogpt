"""诊断豆包流式延迟：打印首个 token、每个 token、结束的时间。

用法：
    export volc_api_key="ark-xxxx..."
    python3 test_doubao_stream.py
"""

import asyncio
import os
import time

from xiaogpt.bot import get_bot
from xiaogpt.config import Config


async def main() -> None:
    # 直接从 xiao_config.yaml 读配置，保证 key/模型和 xiaogpt 完全一致
    import os.path
    cfg_path = os.path.join(os.path.dirname(__file__), "xiao_config.yaml")
    cfg = Config(**Config.read_from_file(cfg_path))
    bot = get_bot(cfg)
    print(f"用模型：{cfg.gpt_options.get('model')}")
    t0 = time.perf_counter()
    first_t = None
    count = 0
    print("提问：讲个笑话")
    async for chunk in bot.ask_stream("讲个笑话", **cfg.gpt_options):
        if first_t is None:
            first_t = time.perf_counter()
            print(f"\n[首个 token 用时 {first_t - t0:.2f}s]")
        count += 1
    print(f"\n[共 {count} 个 chunk，总用时 {time.perf_counter() - t0:.2f}s]")
    if first_t:
        print(f"[首 token 到结束 {time.perf_counter() - first_t:.2f}s]")


if __name__ == "__main__":
    asyncio.run(main())
