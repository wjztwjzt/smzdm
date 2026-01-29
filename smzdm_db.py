import os
import sqlite3
from typing import Iterable, Dict, Any, Tuple, Optional
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(__file__), "smzdm.db")


def _get_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """
    初始化 sqlite3 数据库。

    按需求建立三张表：
    1) checkin_logs：签到 & 资产变动记录（账号、碎银、金币、时间）
    2) gift_items：商品信息（由 smzdm_chaxun.py 爬取）
    3) exchange_logs：兑换记录（由兑换脚本写入）
    """
    conn = _get_conn()
    cur = conn.cursor()

    # 签到/资产记录表
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS checkin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account INTEGER NOT NULL,
            silver INTEGER NOT NULL,
            gold INTEGER NOT NULL,
            ts TEXT NOT NULL,
            remark TEXT DEFAULT ''
        )
        """
    )

    # 礼品信息表（兑换页商品）
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS gift_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gift_id TEXT NOT NULL,
            name TEXT NOT NULL,
            cost_value INTEGER NOT NULL,
            cost_type TEXT NOT NULL,          -- 'silver' / 'gold'
            remaining INTEGER DEFAULT 0,
            claimed INTEGER DEFAULT 0,
            data_pre_p TEXT DEFAULT '',
            price_text TEXT DEFAULT '',
            last_seen_ts TEXT NOT NULL
        )
        """
    )

    # 兑换记录表
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS exchange_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account INTEGER NOT NULL,
            gift_id TEXT NOT NULL,
            gift_name TEXT NOT NULL,
            code TEXT DEFAULT '',
            cost_value INTEGER NOT NULL,
            cost_type TEXT NOT NULL,
            ts TEXT NOT NULL,
            status TEXT NOT NULL              -- success / fail / pending
        )
        """
    )

    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def record_checkin(account: int, silver: int, gold: int, remark: str = "checkin") -> None:
    """记录一次签到/资产快照。"""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO checkin_logs(account, silver, gold, ts, remark) VALUES (?,?,?,?,?)",
        (account, int(silver), int(gold), _now(), remark),
    )
    conn.commit()
    conn.close()


def get_latest_balance(account: int) -> Tuple[int, int]:
    """
    获取某账号当前碎银/金币（取最近一条记录，没有则返回 0,0）。
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT silver, gold FROM checkin_logs WHERE account=? ORDER BY id DESC LIMIT 1",
        (account,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return 0, 0
    return int(row[0]), int(row[1])


def adjust_balance(account: int, delta_silver: int = 0, delta_gold: int = 0, remark: str = "") -> None:
    """
    在最近一次余额基础上做增减，并再写一条新记录。
    - 任务奖励：delta_silver/delta_gold 为正
    - 兑换扣费：delta_* 为负
    """
    silver, gold = get_latest_balance(account)
    new_silver = max(0, silver + int(delta_silver))
    new_gold = max(0, gold + int(delta_gold))
    record_checkin(account, new_silver, new_gold, remark or "adjust")


def save_gift_items(items: Iterable[Dict[str, Any]]) -> None:
    """
    批量保存兑换页礼品信息。
    约定 item 字段：
    - gift_id, name, cost_value, cost_type, remaining, claimed, data_pre_p, price_text
    """
    conn = _get_conn()
    cur = conn.cursor()
    ts = _now()

    for it in items:
        gift_id = str(it.get("gift_id", "")).strip()
        name = str(it.get("name", "")).strip()
        if not gift_id or not name:
            continue

        cost_value = int(it.get("cost_value") or 0)
        cost_type = str(it.get("cost_type") or "silver").strip()
        remaining = int(it.get("remaining") or 0)
        claimed = int(it.get("claimed") or 0)
        data_pre_p = str(it.get("data_pre_p") or "")
        price_text = str(it.get("price_text") or "")

        # 简单 upsert：按 gift_id 覆盖
        cur.execute(
            """
            SELECT id FROM gift_items WHERE gift_id=? LIMIT 1
            """,
            (gift_id,),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                """
                UPDATE gift_items
                SET name=?, cost_value=?, cost_type=?, remaining=?, claimed=?,
                    data_pre_p=?, price_text=?, last_seen_ts=?
                WHERE gift_id=?
                """,
                (
                    name,
                    cost_value,
                    cost_type,
                    remaining,
                    claimed,
                    data_pre_p,
                    price_text,
                    ts,
                    gift_id,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO gift_items
                    (gift_id, name, cost_value, cost_type, remaining, claimed,
                     data_pre_p, price_text, last_seen_ts)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    gift_id,
                    name,
                    cost_value,
                    cost_type,
                    remaining,
                    claimed,
                    data_pre_p,
                    price_text,
                    ts,
                ),
            )

    conn.commit()
    conn.close()


def pick_best_affordable_gift(silver: int) -> Optional[Dict[str, Any]]:
    """
    挑选当前碎银可兑换的最高档礼品（只看 cost_type='silver'）。
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT gift_id, name, cost_value, cost_type
        FROM gift_items
        WHERE cost_type='silver' AND cost_value <= ? AND remaining != 0
        ORDER BY cost_value DESC
        LIMIT 1
        """,
        (int(silver),),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "gift_id": str(row[0]),
        "name": str(row[1]),
        "cost_value": int(row[2]),
        "cost_type": str(row[3]),
    }


def record_exchange(
    account: int,
    gift_id: str,
    gift_name: str,
    code: str,
    cost_value: int,
    cost_type: str,
    status: str,
) -> None:
    """记录一次兑换结果。"""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO exchange_logs
            (account, gift_id, gift_name, code, cost_value, cost_type, ts, status)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            int(account),
            str(gift_id),
            str(gift_name),
            str(code or ""),
            int(cost_value),
            str(cost_type or "silver"),
            _now(),
            str(status or "success"),
        ),
    )
    conn.commit()
    conn.close()

