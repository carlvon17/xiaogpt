"""生成 ~/.mi.token 的半自动化脚本（应对小米异常登录二次验证）。

来源思路：https://github.com/yihong0618/MiService/issues/61
修复点（相对 issue 原版）：
  1. 只登录 micoapi（xiaomiio 在 passToken 已存在时会 KeyError，且失败会连累清空整个 token）；
     xiaogpt 只要带上 MI_DID 就不会走需要 xiaomiio 的 MiIO 路径，故不需要它。
  2. 兼容「凭已有 passToken 直接通过」的响应（resp 可能只含 location/nonce/ssecurity，不含 userId/passToken）。
  3. 登录失败时不再清空整个 token，避免误删已成功拿到的凭证。

用法：
    export MI_USER="+8613xxxxxxxxx"
    export MI_PASS="你的小米密码"
    python3 mi_token_gen.py

若 ~/.mi.token 已含有效 passToken（例如手动写入的种子），本脚本会用它静默换出
serviceToken，不再触发短信验证。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os

import aiohttp

from miservice import MiAccount, MiTokenStore
from miservice.miaccount import get_random

_LOGGER = logging.getLogger(__name__)


async def custom_login(self: MiAccount, sid: str) -> bool:
    """替换原生 login：处理二次验证，且不清空已成功的 token。"""
    if not self.token:
        self.token = {"deviceId": get_random(16).upper()}
    try:
        resp = await self._serviceLogin(f"serviceLogin?sid={sid}&_json=true")

        # code == 0：已凭 passToken 直接通过，resp 含 location/nonce/ssecurity
        #           （可能不含 userId/passToken，下面按需取）
        if resp.get("code") != 0:
            if "qs" not in resp:
                print("\n❌ [第一步握手失败] 服务器未返回预期的参数 (qs)。")
                print(f"📄 服务器实际返回: {json.dumps(resp, ensure_ascii=False)}")
                if resp.get("code") == 87001:
                    print("\n⚠️ 诊断结果：触发了小米的【图形验证码 / 频繁请求风控】！")
                    print("💡 建议：暂缓几小时再试，或更换网络 IP（如连手机热点）再试。")
                raise Exception(f"握手失败，缺少 qs 参数。详情: {resp}")

            data = {
                "_json": "true",
                "qs": resp["qs"],
                "sid": resp["sid"],
                "_sign": resp["_sign"],
                "callback": resp["callback"],
                "user": self.username,
                "hash": hashlib.md5(self.password.encode()).hexdigest().upper(),
            }
            resp = await self._serviceLogin("serviceLoginAuth2", data)

            if resp.get("code") != 0 and "notificationUrl" not in resp:
                print(f"\n❌ [账号密码验证失败] 返回: {json.dumps(resp, ensure_ascii=False)}")
                if resp.get("code") == 70016:
                    print("⚠️ 诊断结果：密码不正确！请检查 MI_PASS 是否正确。")
                raise Exception(f"验证失败: {resp}")

            # --- 处理二次验证（短信验证码）---
            if "userId" not in resp:
                notification_url = resp.get("notificationUrl")
                if not notification_url:
                    raise Exception(f"无 userId 且无 notificationUrl: {resp}")

                print("\n" + "=" * 60)
                print("⚠️  需要短信验证码验证")
                print("请按以下步骤操作：")
                print("1. 在浏览器中打开下方链接（可右键复制）：")
                print(f"   {notification_url}\n")
                print("2. 点击「发送验证码」，输入手机收到的验证码并提交")
                print("3. 验证成功后，浏览器可能跳 401，没关系，打开")
                print("   https://account.xiaomi.com 完成登录")
                print("4. 打开开发者工具 (F12) → Application (存储) → Cookies")
                print("5. 找到 https://account.xiaomi.com 域下的以下两个值：")
                print("   - passToken (较长字符串)")
                print("   - userId (纯数字)\n")

                pass_token = input("请粘贴 passToken: ").strip()
                user_id = input("请粘贴 userId (纯数字): ").strip()
                if not pass_token or not user_id:
                    raise Exception("未提供 passToken 或 userId，登录中止")

                self.token["passToken"] = pass_token
                self.token["userId"] = user_id

                print("正在使用提供的 token 重新验证...")
                resp = await self._serviceLogin("serviceLoginAuth2", data)
                if resp.get("code") != 0 or "userId" not in resp:
                    raise Exception(f"二次验证后登录失败: {resp}")
                print("✅ 二次验证通过，继续获取 serviceToken...")

        # 只在 resp 提供时更新（直接通过路径可能不返回 userId/passToken）
        if "userId" in resp:
            self.token["userId"] = resp["userId"]
        if "passToken" in resp:
            self.token["passToken"] = resp["passToken"]

        if "location" not in resp:
            raise Exception(f"登录响应缺少 location: {resp}")

        service_token = await self._securityTokenService(
            resp["location"], resp["nonce"], resp["ssecurity"]
        )
        self.token[sid] = (resp["ssecurity"], service_token)
        if self.token_store:
            self.token_store.save_token(self.token)
        return True

    except Exception as e:  # noqa: BLE001
        # 关键修复：不再清空整个 token，避免误删已成功的 sid 凭证
        _LOGGER.exception("Exception on login %s: %s", self.username, e)
        return False


# 猴子补丁：替换原生库的 login 方法
MiAccount.login = custom_login


async def main() -> None:
    mi_user = os.getenv("MI_USER", "")
    mi_pass = os.getenv("MI_PASS", "")
    if not mi_user or not mi_pass:
        print("请先设置环境变量：export MI_USER=... && export MI_PASS=...")
        return

    token_path = os.path.join(os.path.expanduser("~"), ".mi.token")
    print(f"准备生成小米凭证到: {token_path}")

    store = MiTokenStore(token_path)
    async with aiohttp.ClientSession() as session:
        account = MiAccount(session, mi_user, mi_pass, store)
        ok = await account.login("micoapi")
        print(f"[micoapi] login -> {'✅' if ok else '❌'}")
        if ok:
            print(f"\n🎉 凭证获取成功！已保存至 {token_path}")
        else:
            print("\n❌ 凭证获取失败，请根据上方的日志排查问题。")


if __name__ == "__main__":
    asyncio.run(main())
