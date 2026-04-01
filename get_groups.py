import asyncio, os
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat
from db import Database
from broadcast import build_proxy

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

async def get_groups_for_account(account):
    phone = account["phone"]
    session_path = f"sessions/session_{phone.replace('+', '')}"
    proxy = build_proxy(account)  # 复用 broadcast.py 里的 build_proxy

    client = TelegramClient(session_path, API_ID, API_HASH, proxy=proxy)
    await client.connect()
    if not await client.is_user_authorized():
        print(f"[{phone}] 未登录，跳过")
        await client.disconnect()
        return []

    groups = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, (Channel, Chat)):
            try:
                username = entity.username
            except AttributeError:
                username = None

            if not username:  # 跳过私有群
                continue

            link = f"https://t.me/{username}"
            groups.append((dialog.name, link))

    await client.disconnect()
    return groups

async def main():
    db = Database()
    accounts = db.get_active_accounts()
    all_groups = {}

    for acc in accounts:
        print(f"\n--- {acc['phone']} ---")
        groups = await get_groups_for_account(acc)
        for name, link in groups:
            print(f"  {name}  |  {link}")
            all_groups[link] = name  # 去重

    print(f"\n\n共 {len(all_groups)} 个不重复群")

asyncio.run(main())