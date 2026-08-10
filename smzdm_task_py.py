import os
from typing import Any, Dict, List, Tuple

from smzdm_bot import get_env_cookies, request_api, remove_tags, wait
from smzdm_tasklib import SmzdmTaskBot
from smzdm_db import init_db, adjust_balance
import re
from dotenv import load_dotenv
import os
import random

load_dotenv()

class SmzdmNormalTaskBot(SmzdmTaskBot):
    def __init__(self, cookie: str, account_index: int = 1) -> None:
        super().__init__(cookie)
        self.account_index = int(account_index)

    def run(self) -> str:
        self.log("获取任务列表")
        tasks, _detail = self.get_task_list()
        wait(5, 10)

        notify_msg = self.do_tasks(tasks)

        self.log("查询是否有限时累计活动阶段奖励")
        wait(5, 15)

        _tasks2, detail2 = self.get_task_list()
        cell_data = (detail2.get("cell_data") or {}) if isinstance(detail2, dict) else {}

        if cell_data and str(cell_data.get("activity_reward_status", "")) == "1":
            self.log("有奖励，领取奖励")
            wait(5, 15)
            ok = self.receive_activity(cell_data).get("isSuccess", False)
            notify_msg += f"{'🟢' if ok else '❌'}限时累计活动阶段奖励领取{'成功' if ok else '失败！请查看日志'}\n"
        else:
            self.log("无奖励")

        return notify_msg or "无可执行任务"

    def get_task_list(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        resp = request_api(
            "https://user-api.smzdm.com/task/list_v2",
            method="post",
            headers=self.get_headers(),
        )
        if not resp["isSuccess"]:
            self.log(f"任务列表获取失败！{resp['response']}")
            return [], {}

        rows = ((resp["data"].get("data") or {}).get("rows") or [])
        if not rows:
            self.log(f"任务列表获取失败！{resp['response']}")
            return [], {}

        first = rows[0] or {}
        default_list = (
            (((first.get("cell_data") or {}).get("activity_task") or {}).get("default_list_v2")) or []
        )
        if not default_list:
            self.log(f"任务列表获取失败！{resp['response']}")
            return [], {}

        tasks: List[Dict[str, Any]] = []
        for item in default_list:
            tasks.extend((item or {}).get("task_list") or [])

        return tasks, first

    def receive_activity(self, activity: Dict[str, Any]) -> Dict[str, Any]:
        self.log(f"领取奖励: {activity.get('activity_name','')}")
        resp = request_api(
            "https://user-api.smzdm.com/task/activity_receive",
            method="post",
            headers=self.get_headers(),
            data={"activity_id": activity.get("activity_id")},
        )
        if resp["isSuccess"]:
            reward_msg = remove_tags(((resp["data"].get("data") or {}).get("reward_msg") or ""))
            self.log(reward_msg)

            # 解析奖励中的碎银/金币并写入数据库
            add_silver, add_gold = _parse_reward_delta(reward_msg)
            if add_silver or add_gold:
                adjust_balance(
                    self.account_index,
                    delta_silver=add_silver,
                    delta_gold=add_gold,
                    remark="task_activity_reward",
                )
            return {"isSuccess": True}

        self.log(f"领取奖励失败！{resp['response']}")
        return {"isSuccess": False}

    def receive_reward(self, task_id: str) -> Dict[str, Any]:
        robot_token = self.get_robot_token()
        if not robot_token:
            return {"isSuccess": False, "msg": "领取任务奖励失败！"}

        resp = request_api(
            "https://user-api.smzdm.com/task/activity_task_receive",
            method="post",
            headers=self.get_headers(),
            data={
                "robot_token": robot_token,
                "geetest_seccode": "",
                "geetest_validate": "",
                "geetest_challenge": "",
                "captcha": "",
                "task_id": task_id,
            },
        )
        if resp["isSuccess"]:
            msg = remove_tags(((resp["data"].get("data") or {}).get("reward_msg") or ""))
            self.log(msg)

            # 解析奖励中的碎银/金币并写入数据库
            add_silver, add_gold = _parse_reward_delta(msg)
            if add_silver or add_gold:
                adjust_balance(
                    self.account_index,
                    delta_silver=add_silver,
                    delta_gold=add_gold,
                    remark="task_reward",
                )
            return {"isSuccess": True, "msg": msg}

        self.log(f"领取任务奖励失败！{resp['response']}")
        return {"isSuccess": False, "msg": "领取任务奖励失败！"}


def _parse_reward_delta(text: str) -> Tuple[int, int]:
    """
    从奖励描述中提取增加的碎银/金币数量。
    示例："...获得10碎银，5金币..."。
    """
    silver = 0
    gold = 0
    if not text:
        return 0, 0

    for m in re.finditer(r"(\d+)\s*碎银", text):
        try:
            silver += int(m.group(1))
        except Exception:
            continue
    for m in re.finditer(r"(\d+)\s*金币", text):
        try:
            gold += int(m.group(1))
        except Exception:
            continue
    return silver, gold


def main() -> None:
    # 确保数据库已初始化
    init_db()

    cookies = get_env_cookies()
    if not cookies:
        print("\n请先设置 SMZDM_COOKIE 环境变量")
        return

    notify_content = ""
    for i, cookie in enumerate(cookies):
        if not cookie:
            continue
        if i > 0:
            print()
            wait(10, 30)
            print()

        sep = f"\n****** 账号{i + 1} ******\n"
        print(sep)

        bot = SmzdmNormalTaskBot(cookie, account_index=i + 1)
        msg = bot.run()
        notify_content += f"{sep}{msg}\n"

    # Python 版本默认直接输出；如你需要对接青龙通知，可再做 sendNotify 迁移
    print("\n" + notify_content)


if __name__ == "__main__":
    main()
