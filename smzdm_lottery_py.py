import re
import time
from typing import Any, Dict, Optional

from smzdm_bot import SmzdmBot, get_env_cookies, parse_json, request_api, wait


class SmzdmLotteryBot(SmzdmBot):
    def run(self) -> str:
        notify_msg = ""

        vip_id1 = self.get_activity_id_from_vip("https://m.smzdm.com/topic/bwrzf5/516lft")
        if vip_id1:
            wait(3, 10)
            notify_msg += f"转盘抽奖ID: {vip_id1}\n"
            notify_msg += self.draw(vip_id1)
            notify_msg += "\n\n"

        print()
        wait(5, 15)
        print()

        vip_id2 = self.get_activity_id_from_vip("https://m.smzdm.com/topic/zhyzhuanpan/cjzp/")
        if vip_id2:
            wait(3, 10)
            notify_msg += f"转盘抽奖ID: {vip_id2}\n"
            notify_msg += self.draw(vip_id2)

        return notify_msg

    def draw(self, active_id: str) -> str:
        callback = f"jQuery34107538452897131465_{int(time.time() * 1000)}"
        resp = request_api(
            "https://zhiyou.smzdm.com/user/lottery/jsonp_draw",
            method="get",
            sign=False,
            parse_json_resp=False,
            headers={
                **self.get_headers_for_web(),
                "x-requested-with": "com.smzdm.client.android",
                "Referer": "https://m.smzdm.com/",
            },
            data={"active_id": active_id, "callback": callback},
        )

        if not resp["isSuccess"]:
            print(f"转盘抽奖失败，接口响应异常: {resp['response']}")
            return "转盘抽奖失败，接口响应异常"

        raw = resp["data"]
        m = re.search(r"\((.*)\)", raw or "")
        if not m:
            print(f"转盘抽奖失败，接口响应异常: {resp['response']}")
            return "转盘抽奖失败，接口响应异常"

        result = parse_json(m.group(1))
        try:
            code = int(result.get("error_code"))
        except Exception:
            code = -999

        if code in (0, 1, 4):
            msg = str(result.get("error_msg", ""))
            print(msg)
            return msg

        print(f"转盘抽奖失败，接口响应异常：{resp['response']}")
        return "转盘抽奖失败，接口响应异常"

    def get_activity_id_from_vip(self, url: str) -> Optional[str]:
        resp = request_api(
            url,
            method="get",
            sign=False,
            parse_json_resp=False,
            headers={**self.get_headers_for_web(), "x-requested-with": "com.smzdm.client.android"},
        )
        if not resp["isSuccess"]:
            print(f"获取转盘抽奖失败: {resp['response']}")
            return None

        html = resp["data"]
        m = re.search(r'\\"hashId\\":\\"([^\\]+)\\"', html or "", re.I)
        if m:
            print(f"转盘抽奖ID: {m.group(1)}")
            return m.group(1)

        print("未找到转盘抽奖ID")
        return None


def main() -> None:
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

        bot = SmzdmLotteryBot(cookie)
        msg = bot.run()
        notify_content += sep + msg + "\n"

    print("\n" + notify_content)


if __name__ == "__main__":
    main()
