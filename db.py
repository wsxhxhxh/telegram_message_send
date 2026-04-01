"""
数据库模块 —— 管理账号（含代理）、群链接、发送记录
"""

import sqlite3

DB_PATH = "broadcast.db"


class Database:
    def __init__(self, path: str = DB_PATH):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()
        self._migrate()

    # ----------------------------------------------------------
    # 建表
    # ----------------------------------------------------------
    def _init_tables(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            phone        TEXT    NOT NULL UNIQUE,
            note         TEXT    DEFAULT '',
            status       TEXT    DEFAULT 'active',
            proxy_type   TEXT    DEFAULT '',
            proxy_host   TEXT    DEFAULT '',
            proxy_port   INTEGER DEFAULT 0,
            proxy_user   TEXT    DEFAULT '',
            proxy_pass   TEXT    DEFAULT '',
            created_at   TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS groups (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            link        TEXT    NOT NULL UNIQUE,
            note        TEXT    DEFAULT '',
            active      INTEGER DEFAULT 1,
            created_at  TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS send_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id  INTEGER NOT NULL REFERENCES accounts(id),
            group_id    INTEGER NOT NULL REFERENCES groups(id),
            stage       TEXT    NOT NULL,
            success     INTEGER NOT NULL,
            message     TEXT    DEFAULT '',
            note        TEXT    DEFAULT '',
            created_at  TEXT    DEFAULT (datetime('now','localtime'))
        );
        """)
        self.conn.commit()

    def _migrate(self):
        """兼容旧数据库：自动补齐缺少的代理字段"""
        existing = {
            row[1]
            for row in self.conn.execute("PRAGMA table_info(accounts)").fetchall()
        }
        new_cols = {
            "proxy_type": "TEXT DEFAULT ''",
            "proxy_host": "TEXT DEFAULT ''",
            "proxy_port": "INTEGER DEFAULT 0",
            "proxy_user": "TEXT DEFAULT ''",
            "proxy_pass": "TEXT DEFAULT ''",
        }
        for col, definition in new_cols.items():
            if col not in existing:
                self.conn.execute(
                    f"ALTER TABLE accounts ADD COLUMN {col} {definition}"
                )
        self.conn.commit()

    # ----------------------------------------------------------
    # 账号
    # ----------------------------------------------------------
    def add_account(
        self,
        phone: str,
        note: str = "",
        proxy_type: str = "",
        proxy_host: str = "",
        proxy_port: int = 0,
        proxy_user: str = "",
        proxy_pass: str = "",
    ) -> int:
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO accounts
               (phone, note, proxy_type, proxy_host, proxy_port, proxy_user, proxy_pass)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (phone, note, proxy_type, proxy_host, proxy_port, proxy_user, proxy_pass),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_proxy(
        self,
        phone: str,
        proxy_type: str,
        proxy_host: str,
        proxy_port: int,
        proxy_user: str = "",
        proxy_pass: str = "",
    ):
        self.conn.execute(
            """UPDATE accounts
               SET proxy_type=?, proxy_host=?, proxy_port=?, proxy_user=?, proxy_pass=?
               WHERE phone=?""",
            (proxy_type, proxy_host, proxy_port, proxy_user, proxy_pass, phone),
        )
        self.conn.commit()

    def clear_proxy(self, phone: str):
        self.conn.execute(
            """UPDATE accounts
               SET proxy_type='', proxy_host='', proxy_port=0, proxy_user='', proxy_pass=''
               WHERE phone=?""",
            (phone,),
        )
        self.conn.commit()

    def get_active_accounts(self) -> list:
        rows = self.conn.execute(
            "SELECT * FROM accounts WHERE status = 'active' ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    def update_account_status(self, account_id: int, status: str):
        self.conn.execute(
            "UPDATE accounts SET status = ? WHERE id = ?", (status, account_id)
        )
        self.conn.commit()

    # ----------------------------------------------------------
    # 群
    # ----------------------------------------------------------
    def add_group(self, link: str, note: str = "") -> int:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO groups (link, note) VALUES (?, ?)", (link, note)
        )
        self.conn.commit()
        return cur.lastrowid

    def get_active_groups(self) -> list:
        rows = self.conn.execute(
            "SELECT * FROM groups WHERE active = 1 ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    def disable_group(self, group_id: int):
        self.conn.execute("UPDATE groups SET active = 0 WHERE id = ?", (group_id,))
        self.conn.commit()

    # ----------------------------------------------------------
    # 记录
    # ----------------------------------------------------------
    def record_send(
        self,
        account_id: int,
        group_id: int,
        stage: str,
        success: bool,
        note: str = "",
        message: str = "",
    ):
        self.conn.execute(
            """INSERT INTO send_logs (account_id, group_id, stage, success, message, note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (account_id, group_id, stage, int(success), message, note),
        )
        self.conn.commit()

    # ----------------------------------------------------------
    # 汇总
    # ----------------------------------------------------------
    def get_summary(self) -> dict:
        row = self.conn.execute("""
            SELECT
                SUM(CASE WHEN stage='join' AND success=1 THEN 1 ELSE 0 END) AS join_ok,
                SUM(CASE WHEN stage='send' AND success=1 THEN 1 ELSE 0 END) AS send_ok,
                SUM(CASE WHEN success=0 THEN 1 ELSE 0 END)                  AS failed
            FROM send_logs
        """).fetchone()
        return dict(row) if row else {"join_ok": 0, "send_ok": 0, "failed": 0}

    def close(self):
        self.conn.close()

if __name__ == '__main__':
    db = Database(DB_PATH)