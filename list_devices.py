"""列出当前小米账号下所有小爱设备（用 ~/.mi.token 缓存，无需登录）。"""

import asyncio
import json
import os

import aiohttp

from miservice import MiAccount, MiTokenStore
from miservice.minaservice import MiNAService

TOKEN_PATH = os.path.join(os.path.expanduser("~"), ".mi.token")


async def main() -> None:
    store = MiTokenStore(TOKEN_PATH)
    async with aiohttp.ClientSession() as session:
        account = MiAccount(session, os.getenv("MI_USER", ""), os.getenv("MI_PASS", ""), store)
        mina = MiNAService(account)
        devices = await mina.device_list()
        if not devices:
            print("设备列表为空：这台音箱可能没绑定到当前小米账号。")
            return
        print(f"共 {len(devices)} 台设备：\n")
        for i, d in enumerate(devices, 1):
            print(f"--- 设备 {i} ---")
            print(f"  name        : {d.get('name')}")
            print(f"  hardware    : {d.get('hardware')}")
            print(f"  model       : {d.get('model')}")
            print(f"  deviceID    : {d.get('deviceID')}")
            print(f"  miotDID     : {d.get('miotDID')}")
            print(f"  serial      : {d.get('serialNumber')}")
        print("\n完整 JSON（供调试）：")
        print(json.dumps(devices, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
