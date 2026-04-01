"""
Telegram 多账号自动加群 + 错峰群发消息工具（基于 Telethon）
每个账号使用各自在数据库中配置的代理
"""

import asyncio
import random
import logging
import os
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import (
    FloodWaitError,
    UserAlreadyParticipantError,
    InviteHashExpiredError,
    ChannelPrivateError,
    PeerFloodError,
)
from db import Database

# ============================================================
# 配置
# ============================================================
API_ID   = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

MESSAGES = [
    "收购 xxx，有的朋友私信我，价格好说 🙏",
    "求购 xxx，有货的联系我，诚心收，价格面议",
    "想收 xxx，哪位有？欢迎私聊我",
]

JOIN_WAIT_MIN        = 5
JOIN_WAIT_MAX        = 15
SEND_WAIT_MIN        = 60
SEND_WAIT_MAX        = 120
ACCOUNT_STAGGER_MIN  = 30
ACCOUNT_STAGGER_MAX  = 90

SESSION_DIR = "sessions"

# ============================================================
# 日志
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("broadcast.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ============================================================
# 代理解析
# ============================================================
def build_proxy(account: dict):
    """
    把数据库中的代理字段转成 Telethon 需要的格式。
    返回 None 表示不使用代理。
    支持：socks5 / socks4 / http
    """
    ptype = account.get("proxy_type", "").strip().lower()
    phost = account.get("proxy_host", "").strip()
    pport = account.get("proxy_port", 0)

    if not ptype or not phost or not pport:
        return None

    import socks  # PySocks，telethon 会自动安装
    type_map = {
        "socks5": socks.SOCKS5,
        "socks4": socks.SOCKS4,
        "http":   socks.HTTP,
    }
    socks_type = type_map.get(ptype)
    if socks_type is None:
        logger.warning(f"未知代理类型: {ptype}，跳过代理")
        return None

    user = account.get("proxy_user", "") or None
    pwd  = account.get("proxy_pass", "") or None

    # Telethon proxy 元组格式：(type, host, port, rdns, username, password)
    return (socks_type, phost, int(pport), True, user, pwd)


# ============================================================
# 加群
# ============================================================
async def join_group(client, group_link: str):
    try:
        if "+=" in group_link or "/+" in group_link:
            hash_part = group_link.split("+")[-1]
            await client(ImportChatInviteRequest(hash_part))
        else:
            username = group_link.replace("https://t.me/", "").replace("@", "").strip("/")
            await client(JoinChannelRequest(username))
        return True, "加入成功"
    except UserAlreadyParticipantError:
        return True, "已在群中"
    except FloodWaitError as e:
        logger.warning(f"加群限流，等待 {e.seconds}s ...")
        await asyncio.sleep(e.seconds)
        return False, f"限流 {e.seconds}s"
    except InviteHashExpiredError:
        return False, "邀请链接已过期"
    except ChannelPrivateError:
        return False, "群已设为私有"
    except Exception as e:
        return False, f"加群异常: {e}"


# ============================================================
# 发消息
# ============================================================
async def send_message(client, group_link: str, message: str):
    username = ''
    try:
        username = group_link.replace("https://t.me/", "").replace("@", "").strip("/")
        await client.send_message(username, message)
        return True, "发送成功"
    except FloodWaitError as e:
        logger.warning(f"发消息限流，等待 {e.seconds}s ...")
        await asyncio.sleep(e.seconds)
        try:
            if username:
                await client.send_message(username, message)
                return True, "限流后重试成功"
        except Exception as e2:
            return False, f"重试失败: {e2}"
    except PeerFloodError:
        return False, "PeerFlood：账号被限制"
    except Exception as e:
        return False, f"发送异常: {e}"


# ============================================================
# 单账号任务
# ============================================================
async def run_account(db: Database, account: dict, groups: list, stagger_delay: float):
    phone        = account["phone"]
    session_name = os.path.join(SESSION_DIR, f"session_{phone.lstrip('+')}")
    proxy        = build_proxy(account)

    if stagger_delay > 0:
        logger.info(f"[{phone}] 错峰等待 {stagger_delay:.0f}s 后开始...")
        await asyncio.sleep(stagger_delay)

    proxy_desc = f"{account['proxy_type']}://{account['proxy_host']}:{account['proxy_port']}" \
                 if proxy else "无代理"
    logger.info(f"[{phone}] 使用代理: {proxy_desc}")

    client = TelegramClient(session_name, API_ID, API_HASH, proxy=proxy)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.error(f"[{phone}] ❌ Session 未授权，请先运行 login.py 重新登录")
            db.update_account_status(account["id"], "login_failed")
            return
        logger.info(f"[{phone}] ✅ 登录成功")
    except Exception as e:
        logger.error(f"[{phone}] ❌ 登录失败: {e}")
        db.update_account_status(account["id"], "login_failed")
        return

    db.update_account_status(account["id"], "active")
    total = len(groups)

    for idx, group in enumerate(groups, 1):
        group_link = group["link"]
        group_id   = group["id"]
        logger.info(f"[{phone}] [{idx}/{total}] 处理: {group_link}")

        join_ok, join_reason = await join_group(client, group_link)
        logger.info(f"[{phone}]   加群: {'✅' if join_ok else '❌'} {join_reason}")
        db.record_send(account["id"], group_id, "join", join_ok, join_reason)

        if not join_ok:
            continue

        wait = random.uniform(JOIN_WAIT_MIN, JOIN_WAIT_MAX)
        logger.info(f"[{phone}]   等待 {wait:.0f}s 后发消息...")
        await asyncio.sleep(wait)

        message = random.choice(MESSAGES)
        send_ok, send_reason = await send_message(client, group_link, message)
        logger.info(f"[{phone}]   发消息: {'✅' if send_ok else '❌'} {send_reason}")
        db.record_send(account["id"], group_id, "send", send_ok, send_reason, message)

        if not send_ok and "PeerFlood" in send_reason:
            logger.error(f"[{phone}] ⛔ PeerFlood，停止该账号！")
            db.update_account_status(account["id"], "peer_flood")
            break

        if idx < total:
            wait = random.uniform(SEND_WAIT_MIN, SEND_WAIT_MAX)
            logger.info(f"[{phone}]   等待 {wait:.0f}s 处理下一个群...")
            await asyncio.sleep(wait)

    await client.disconnect()
    logger.info(f"[{phone}] 全部完成")


# ============================================================
# 主流程
# ============================================================
async def main():
    os.makedirs(SESSION_DIR, exist_ok=True)

    db       = Database()
    accounts = db.get_active_accounts()
    all_groups = db.get_active_groups()

    if not accounts:
        logger.error("没有可用账号")
        return
    if not all_groups:
        logger.error("没有目标群")
        return

    logger.info(f"共 {len(accounts)} 个账号，{len(all_groups)} 个目标群")

    tasks = []
    for i, account in enumerate(accounts):
        # 查出该账号已发送过的群组
        sent_ids = db.get_sent_group_ids(account["id"])

        # 过滤掉已发送的群组
        available = [g for g in all_groups if g["id"] not in sent_ids]

        if not available:
            logger.info(f"[{account['phone']}] 所有群组均已发送过，跳过")
            continue

        # 随机打乱，再平均分配
        random.shuffle(available)
        chunk_size = max(1, len(available) // len(accounts))
        assigned = available[i * chunk_size: (i + 1) * chunk_size]

        # 最后一个账号接收剩余群组，避免遗漏
        if i == len(accounts) - 1:
            assigned = available[i * chunk_size:]

        if not assigned:
            continue

        delay = i * random.randint(ACCOUNT_STAGGER_MIN, ACCOUNT_STAGGER_MAX)
        tasks.append(run_account(db, account, assigned, delay))

    if tasks:
        await asyncio.gather(*tasks)

    logger.info("\n" + "=" * 50)
    s = db.get_summary()
    logger.info(f"📊 加群成功: {s['join_ok']} | 发送成功: {s['send_ok']} | 失败: {s['failed']}")
    db.close()


if __name__ == "__main__":
    asyncio.run(main())
