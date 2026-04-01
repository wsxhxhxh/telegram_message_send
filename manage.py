"""
manage.py —— 命令行管理工具

账号管理：
  python manage.py add-account <phone> [备注]
  python manage.py set-proxy   <phone> <socks5|socks4|http> <host> <port> [user] [pass]
  python manage.py clear-proxy <phone>
  python manage.py disable-account <phone>
  python manage.py list-accounts

群管理：
  python manage.py add-group   <link> [备注]
  python manage.py disable-group <id>
  python manage.py list-groups

记录：
  python manage.py list-logs
  python manage.py summary
"""

import sys
from db import Database


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    db  = Database()
    cmd = sys.argv[1]

    # ── 账号 ──────────────────────────────────────────────
    if cmd == "add-account":
        if len(sys.argv) < 3:
            print("用法: python manage.py add-account <phone> [备注]")
            sys.exit(1)
        phone = sys.argv[2]
        note  = sys.argv[3] if len(sys.argv) > 3 else ""
        db.add_account(phone, note)
        print(f"✅ 账号已添加: {phone}（代理未设置，可用 set-proxy 配置）")

    elif cmd == "set-proxy":
        # set-proxy <phone> <type> <host> <port> [user] [pass]
        if len(sys.argv) < 6:
            print("用法: python manage.py set-proxy <phone> <socks5|socks4|http> <host> <port> [user] [pass]")
            sys.exit(1)
        phone      = sys.argv[2]
        ptype      = sys.argv[3].lower()
        phost      = sys.argv[4]
        pport      = int(sys.argv[5])
        puser      = sys.argv[6] if len(sys.argv) > 6 else ""
        ppass      = sys.argv[7] if len(sys.argv) > 7 else ""
        db.update_proxy(phone, ptype, phost, pport, puser, ppass)
        auth = f"  认证: {puser}:***" if puser else ""
        print(f"✅ 代理已设置: {phone} → {ptype}://{phost}:{pport}{auth}")

    elif cmd == "clear-proxy":
        if len(sys.argv) < 3:
            print("用法: python manage.py clear-proxy <phone>")
            sys.exit(1)
        db.clear_proxy(sys.argv[2])
        print(f"✅ 代理已清除: {sys.argv[2]}")

    elif cmd == "disable-account":
        if len(sys.argv) < 3:
            print("用法: python manage.py disable-account <phone>")
            sys.exit(1)
        phone = sys.argv[2]
        db.conn.execute("UPDATE accounts SET status='disabled' WHERE phone=?", (phone,))
        db.conn.commit()
        print(f"✅ 账号已禁用: {phone}")

    elif cmd == "list-accounts":
        rows = db.conn.execute("SELECT * FROM accounts ORDER BY id").fetchall()
        print(f"{'ID':<4} {'手机号':<18} {'状态':<14} {'代理':<35} {'备注'}")
        print("-" * 85)
        for r in rows:
            if r["proxy_host"]:
                proxy_str = f"{r['proxy_type']}://{r['proxy_host']}:{r['proxy_port']}"
                if r["proxy_user"]:
                    proxy_str += f" ({r['proxy_user']}:***)"
            else:
                proxy_str = "—"
            print(f"{r['id']:<4} {r['phone']:<18} {r['status']:<14} {proxy_str:<35} {r['note']}")

    # ── 群 ────────────────────────────────────────────────
    elif cmd == "add-group":
        if len(sys.argv) < 3:
            print("用法: python manage.py add-group <link> [备注]")
            sys.exit(1)
        link = sys.argv[2]
        note = sys.argv[3] if len(sys.argv) > 3 else ""
        db.add_group(link, note)
        print(f"✅ 群已添加: {link}")

    elif cmd == "disable-group":
        if len(sys.argv) < 3:
            print("用法: python manage.py disable-group <id>")
            sys.exit(1)
        db.disable_group(int(sys.argv[2]))
        print(f"✅ 群 ID={sys.argv[2]} 已停用")

    elif cmd == "list-groups":
        rows = db.conn.execute("SELECT * FROM groups ORDER BY id").fetchall()
        print(f"{'ID':<4} {'链接':<42} {'启用':<6} {'备注'}")
        print("-" * 65)
        for r in rows:
            print(f"{r['id']:<4} {r['link']:<42} {'是' if r['active'] else '否':<6} {r['note']}")

    # ── 记录 ──────────────────────────────────────────────
    elif cmd == "list-logs":
        rows = db.conn.execute("""
            SELECT l.id, a.phone, g.link, l.stage, l.success, l.note, l.created_at
            FROM send_logs l
            JOIN accounts a ON a.id = l.account_id
            JOIN groups   g ON g.id = l.group_id
            ORDER BY l.id DESC LIMIT 100
        """).fetchall()
        print(f"{'ID':<5} {'手机号':<18} {'群链接':<35} {'阶段':<6} {'结果':<5} {'备注':<25} {'时间'}")
        print("-" * 105)
        for r in rows:
            print(
                f"{r['id']:<5} {r['phone']:<18} {r['link']:<35} "
                f"{r['stage']:<6} {'✅' if r['success'] else '❌':<5} "
                f"{r['note']:<25} {r['created_at']}"
            )

    elif cmd == "summary":
        s = db.get_summary()
        print(f"加群成功: {s['join_ok']}  |  发送成功: {s['send_ok']}  |  失败: {s['failed']}")

    else:
        print(__doc__)

    db.close()


if __name__ == "__main__":
    main()
