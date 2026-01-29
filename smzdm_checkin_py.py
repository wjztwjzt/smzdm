import os
from typing import List, Optional

from Crypto.Cipher import DES
from Crypto.Util.Padding import pad

from smzdm_bot import SmzdmBot, request_api, remove_tags, get_env_cookies, wait, bark_notify
from smzdm_db import init_db, record_checkin


class SmzdmCheckinBot(SmzdmBot):
    """
    Python 版本签到 Bot，对应 smzdm_checkin.js 的主要逻辑。
    """

    def __init__(self, cookie: str, sk: str, account_index: int = 1) -> None:
        super().__init__(cookie)
        self.sk = (sk or "").strip()
        self.account_index = int(account_index)

    def run(self) -> str:
        msg1 = self.checkin()["msg"]
        msg2 = self.all_reward()["msg"]
        msg3 = self.extra_reward()["msg"]
        return f"{msg1}{msg2}{msg3}"

    def checkin(self) -> dict:
        resp = request_api(
            "https://user-api.smzdm.com/checkin",
            method="post",
            headers=self.get_headers(),
            data={
                "touchstone_event": "",
                "sk": self.sk or "1",
                "token": self.token,
                "captcha": "",
            },
        )

        if resp["isSuccess"]:
            data = resp["data"]["data"]
            gold = int(data.get("cgold", 0))
            silver = int(data.get("pre_re_silver", 0))
            msg = (
                f"⭐签到成功{data['daily_num']}天\n"
                f"🏅金币: {gold}\n"
                f"🏅碎银: {silver}\n"
                f"🏅补签卡: {data['cards']}"
            )

            # 记录签到资产快照到数据库
            record_checkin(self.account_index, silver, gold, remark="checkin")

            wait(3, 10)
            vip = self.get_vip_info()
            if vip:
                msg += (
                    f"\n🏅经验: {vip['vip']['exp_current']}\n"
                    f"🏅值会员等级: {vip['vip']['exp_level']}\n"
                    f"🏅值会员经验: {vip['vip']['exp_current_level']}\n"
                    f"🏅值会员有效期至: {vip['vip']['exp_level_expire']}"
                )
            print(msg + "\n")
            return {"isSuccess": True, "msg": msg + "\n\n"}
        else:
            print(f"签到失败！{resp['response']}")
            # 账号失效等情况使用 Bark 通知
            bark_notify("什么值得买签到失败", f"账号{self.account_index} 签到失败，详情：{resp['response']}")
            return {"isSuccess": False, "msg": "签到失败！"}

    def all_reward(self) -> dict:
        resp = request_api(
            "https://user-api.smzdm.com/checkin/all_reward",
            method="post",
            headers=self.get_headers(),
            debug=bool(os.getenv("SMZDM_DEBUG")),
        )

        if resp["isSuccess"]:
            data = resp["data"]["data"]["normal_reward"]
            msg1 = f"{data['reward_add']['title']}: {data['reward_add']['content']}"
            if data["gift"]["title"]:
                msg2 = f"{data['gift']['title']}: {data['gift']['content_str']}"
            else:
                msg2 = f"{data['gift']['sub_content']}"
            print(msg1 + "\n" + msg2 + "\n")
            return {"isSuccess": True, "msg": f"{msg1}\n{msg2}\n\n"}
        else:
            data = resp.get("data") or {}
            if isinstance(data, dict) and data.get("error_code") != "4":
                print(f"查询奖励失败！{resp['response']}")
            return {"isSuccess": False, "msg": ""}

    def extra_reward(self) -> dict:
        if not self.is_continue_checkin():
            msg = "今天没有额外奖励"
            print(msg + "\n")
            return {"isSuccess": False, "msg": msg + "\n"}

        wait(5, 10)

        resp = request_api(
            "https://user-api.smzdm.com/checkin/extra_reward",
            method="post",
            headers=self.get_headers(),
        )

        if resp["isSuccess"]:
            data = resp["data"]["data"]
            msg = f"{data['title']}: {remove_tags(data['gift']['content'])}"
            print(msg)
            return {"isSuccess": True, "msg": msg + "\n"}
        else:
            print(f"领取额外奖励失败！{resp['response']}")
            return {"isSuccess": False, "msg": ""}

    def is_continue_checkin(self) -> bool:
        resp = request_api(
            "https://user-api.smzdm.com/checkin/show_view_v2",
            method="post",
            headers=self.get_headers(),
        )
        if resp["isSuccess"]:
            rows = resp["data"]["data"]["rows"]
            target = next((r for r in rows if r.get("cell_type") == "18001"), None)
            if not target:
                return False
            return bool(
                target["cell_data"]["checkin_continue"]["continue_checkin_reward_show"]
            )
        else:
            print(f"查询是否有额外奖励失败！{resp['response']}")
            return False

    def get_vip_info(self) -> Optional[dict]:
        resp = request_api(
            "https://user-api.smzdm.com/vip",
            method="post",
            headers=self.get_headers(),
            data={"token": self.token},
        )
        if resp["isSuccess"]:
            return resp["data"]["data"]
        else:
            print(f"查询信息失败！{resp['response']}")
            return None


def _random32() -> str:
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return "".join(os.urandom(1)[0] % len(chars) and chars[os.urandom(1)[0] % len(chars)] or chars[0] for _ in range(32))


def _get_device_id(cookie: str) -> str:
    import re

    m = re.search(r"device_id=([^;]*)", cookie)
    if m:
        return m.group(1)
    return _random32()


def calc_sk(cookie: str) -> str:
    """
    尽量复刻 JS 中的 getSk：
    CryptoJS.DES.encrypt(userId + deviceId, key, { mode: ECB, padding: Pkcs7 })
    """
    import re

    m = re.search(r"smzdm_id=([^;]*)", cookie)
    if not m:
        return ""

    user_id = m.group(1)
    device_id = _get_device_id(cookie)
    plaintext = (user_id + device_id).encode("utf-8")

    # CryptoJS DES 使用 8 字节 key，这里取前 8 个字节
    key = "geZm53XAspb02exN".encode("utf-8")[:8]
    cipher = DES.new(key, DES.MODE_ECB)
    encrypted = cipher.encrypt(pad(plaintext, DES.block_size))
    # 与 CryptoJS 默认保持一致，使用 Base64 文本
    import base64

    return base64.b64encode(encrypted).decode("utf-8")


def _split_env_multi(value: str) -> List[str]:
    if "&" in value:
        return [v for v in value.split("&") if v]
    if "\n" in value:
        return [v for v in value.splitlines() if v]
    return [value]


def main() -> None:
    # 初始化数据库
    init_db()

    cookies = get_env_cookies()
    if not cookies:
        print("\n请先设置 SMZDM_COOKIE 环境变量")
        return

    sks: List[str] = []
    raw_sk = os.getenv("SMZDM_SK")
    if raw_sk:
        sks = _split_env_multi(raw_sk)

    notify_content = []

    for i, cookie in enumerate(cookies):
        if not cookie:
            continue

        sk = sks[i] if i < len(sks) else calc_sk(cookie)

        if i > 0:
            wait(10, 30)

        sep = f"\n****** 账号{i + 1} ******\n"
        print(sep)

        bot = SmzdmCheckinBot(cookie, sk, account_index=i + 1)
        msg = bot.run()
        notify_content.append(sep + msg + "\n")

    print("\n".join(notify_content))


if __name__ == "__main__":
    main()
