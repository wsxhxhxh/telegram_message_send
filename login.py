import asyncio
import os
from telethon import TelegramClient
from db import Database

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_DIR = "sessions"


async def login_account(account: dict):
    phone = account["phone"]
    session_name = os.path.join(SESSION_DIR, f"session_{phone.lstrip('+')}")

    from broadcast import build_proxy  # 复用代理逻辑
    proxy = build_proxy(account)

    client = TelegramClient(session_name, API_ID, API_HASH, proxy=proxy)
    await client.start(
        phone=lambda: phone,  # 自动填手机号，不询问
        code_callback=lambda: input(f"[{phone}] 请输入验证码: ")
    )
    print(f"[{phone}] ✅ 登录并保存 session 成功")
    await client.disconnect()


async def main():
    os.makedirs(SESSION_DIR, exist_ok=True)
    db = Database()
    accounts = db.get_active_accounts()
    db.close()

    for account in accounts:
        await login_account(account)  # 逐个登录，方便输入验证码


asyncio.run(main())