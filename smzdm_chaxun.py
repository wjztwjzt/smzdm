"""
兑换礼品：从数据库读礼品/碎银/金币，重点执行兑换；券码由 smzdm_duihuan1 爬取存库。

环境变量：
- smzdm_duihuan: 兑换用 Cookie，多账号用 # 分隔，如 cookie1#cookie2
- smzdm_safe 或 SMZDM_SAFE: 安全码，多账号用 # 分隔，与 cookie 一一对应（必填，否则跳过兑换）
"""
from __future__ import annotations

import os
import time
import requests
from typing import Iterable

from smzdm_bot import PROXIES, bark_notify
from smzdm_db import (
    init_db,
    get_latest_balance,
    list_gift_items,
    pick_best_affordable_gift,
    record_exchange,
    adjust_balance,
)


UA_PC = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
)


def post_exchange(cookie: str, safe_pass: str, gift_id: str) -> dict:
    """
    POST https://duihuan.smzdm.com/quan/lingqugift/{gift_id}
    """
    url = f"https://duihuan.smzdm.com/quan/lingqugift/{gift_id}"
    headers = {
        "Host": "duihuan.smzdm.com",
        "Connection": "keep-alive",
        "sec-ch-ua-platform": "\"Windows\"",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": UA_PC,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "sec-ch-ua": "\"Google Chrome\";v=\"143\", \"Chromium\";v=\"143\", \"Not A(Brand\";v=\"24\"",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "sec-ch-ua-mobile": "?0",
        "Origin": "https://duihuan.smzdm.com",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": f"https://duihuan.smzdm.com/d/{gift_id}/",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7",
        "Cookie": cookie,
    }
    data = {
        "safe_pass": safe_pass,
        "client_type": "PC",
        "sourcePage": f"https://duihuan.smzdm.com/d/{gift_id}/",
    }

    # 先走 SOCKS5 代理，如果失败再直连
    proxy_enabled = bool(PROXIES)
    last_error: Exception | None = None

    for _ in range(2):
        try:
            resp = requests.post(
                url,
                headers=headers,
                data=data,
                timeout=20,
                proxies=PROXIES if proxy_enabled else None,
            )
            try:
                return resp.json()
            except Exception:
                return {"status_code": resp.status_code, "text": resp.text}
        except Exception as e:
            last_error = e
            if proxy_enabled:
                # 代理失败，关掉代理再试一次
                proxy_enabled = False
                continue
            break

    return {"isSuccess": False, "error": repr(last_error)}


def _iter_full_cookies_and_safe() -> Iterable[tuple[int, str, str]]:
    """
    从环境变量读取 smzdm_duihuan（Cookie）与 安全码（smzdm_safe 或 SMZDM_SAFE）。
    安全码必填，否则该账号跳过兑换。
    """
    raw_cookies = (os.getenv("smzdm_duihuan") or "").strip()
    raw_safe = (os.getenv("smzdm_safe") or os.getenv("SMZDM_SAFE") or "").strip()
    cookies = [c.strip() for c in raw_cookies.split("#") if c.strip()]
    safes = [s.strip() for s in raw_safe.split("#") if s.strip()]
    for idx, ck in enumerate(cookies, start=1):
        safe = safes[idx - 1] if idx - 1 < len(safes) else ""
        yield idx, ck, safe


def main() -> None:
    init_db()

    # 从数据库打印礼品列表
    gifts = list_gift_items()
    print("=== 数据库礼品列表（来自 smzdm_duihuan1 爬取）===")
    if not gifts:
        print("  （暂无，请先运行 smzdm_duihuan1 爬取并写入数据库）")
    else:
        for g in gifts:
            ct = "碎银" if g["cost_type"] == "silver" else "金币"
            print(f"  ID {g['gift_id']} | {g['name']} | {g['cost_value']} {ct} | 剩余 {g['remaining']}")
    print()

    any_account = False
    for idx, cookie, safe_pass in _iter_full_cookies_and_safe():
        any_account = True
        print(f"开始第{idx}个账号自动兑换流程：")
        time.sleep(3)

        # 1. 碎银、金币从数据库获取
        silver, gold = get_latest_balance(idx)
        print(f"  当前碎银: {silver}，金币: {gold}（数据库）")

        # 2. 从商品表选出可兑换的最高价礼品（只看碎银）
        gift = pick_best_affordable_gift(silver)
        if not gift:
            print("  当前碎银不足以兑换任何礼品，跳过。")
            print("-" * 50)
            continue

        gift_id = gift["gift_id"]
        gift_name = gift["name"]
        cost_value = gift["cost_value"]
        cost_type = gift["cost_type"]

        # 3. 安全码通过环境变量获取，未配置则跳过兑换
        if not safe_pass:
            print(
                f"  计划兑换：{gift_name}（ID: {gift_id}），但未配置安全码（smzdm_safe / SMZDM_SAFE），跳过兑换。"
            )
            print("-" * 50)
            continue

        print(
            f"  计划兑换礼品：{gift_name}（ID: {gift_id}，消耗 {cost_value}{'碎银' if cost_type=='silver' else '金币'}）"
        )

        # 4. 执行兑换
        resp = post_exchange(cookie, safe_pass, gift_id)
        ok = False
        if isinstance(resp, dict):
            err_code = str(resp.get("error_code", ""))
            err_msg = str(resp.get("error_msg", resp.get("error", "")))
            if err_code == "0":
                ok = True
                print(f"  兑换接口返回成功：{gift_name}")
            else:
                print(f"  兑换失败：{err_msg or resp}")
                if err_code == "4":
                    bark_notify("什么值得买兑换失败", f"账号{idx} Cookie 失效，请重新更新")
        else:
            print(f"  兑换接口异常：{resp!r}")

        # 5. 写入兑换记录（券码由 smzdm_duihuan1 爬取存库，此处不获取）
        record_exchange(
            account=idx,
            gift_id=gift_id,
            gift_name=gift_name,
            code="",
            cost_value=cost_value,
            cost_type=cost_type,
            status="success" if ok else "fail",
        )

        # 6. 成功时扣减数据库中的碎银/金币，并 Bark 通知
        if ok:
            if cost_type == "silver":
                adjust_balance(idx, delta_silver=-cost_value, remark=f"exchange {gift_id}")
            else:
                adjust_balance(idx, delta_gold=-cost_value, remark=f"exchange {gift_id}")

            bark_notify(
                "什么值得买兑换成功",
                f"账号{idx} 成功兑换 {gift_name}，消耗 {cost_value}{'碎银' if cost_type=='silver' else '金币'}",
            )

        print("-" * 50)

    if not any_account:
        print("未设置 smzdm_duihuan（及 smzdm_safe / SMZDM_SAFE）或未解析到任何账号。")


if __name__ == "__main__":
    main()
