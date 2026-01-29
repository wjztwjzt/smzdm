import os
import re
import time
import random
import hashlib
from typing import Any, Dict, Optional, Tuple, List

import requests
from urllib.parse import quote as urlquote


APP_VERSION = "10.4.26"
APP_VERSION_REV = "866"

DEFAULT_USER_AGENT_APP = (
    f"smzdm_android_V{APP_VERSION} rv:{APP_VERSION_REV} "
    "(Redmi Note 3;Android10.0;zh)smzdmapp"
)
DEFAULT_USER_AGENT_WEB = (
    "Mozilla/5.0 (Linux; Android 10.0; Redmi Build/Redmi Note 3; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
    "Chrome/95.0.4638.74 Mobile Safari/537.36 "
    f"smzdm_android_V{APP_VERSION} rv:{APP_VERSION_REV} "
    " (Redmi;Android10.0;zh) jsbv_1.0.0 webv_2.0 smzdmapp"
)

SIGN_KEY = "apr1$AwP!wRRT$gJ/q.X24poeBInlUJC"

RE_VERSION = re.compile(r"(smzdm_android_V|smzdm\s|iphone_smzdmapp/)([\d.]+)", re.I)
RE_REV = re.compile(r"rv:([\d.]+)", re.I)

# 统一代理配置（如不需要代理，可改为空字典 {}）
PROXIES: Dict[str, str] = {
    "http": "socks5://admin:admin123@172.17.0.1:1080",
    "https": "socks5://admin:admin123@172.17.0.1:1080",
}


def bark_notify(title: str, body: str) -> None:
    """
    使用 Bark 推送通知。

    环境变量：
    - BARK_KEY: 设备 key（必填）
    - BARK_URL: 可选，默认 https://api.day.app
    """
    key = os.getenv("BARK_KEY") or ""
    if not key:
        return

    base = os.getenv("BARK_URL", "https://api.day.app").rstrip("/")
    title_q = urlquote(str(title or ""), safe="")
    body_q = urlquote(str(body or ""), safe="")
    url = f"{base}/{key}/{title_q}/{body_q}"
    try:
        requests.get(url, timeout=5)
    except Exception:
        # 通知失败静默忽略，避免影响主逻辑
        pass


def random_str(length: int = 18) -> str:
    chars = "0123456789"
    return "".join(random.choice(chars) for _ in range(length))


def parse_json(s: str) -> Dict[str, Any]:
    try:
        import json

        return json.loads(s)
    except Exception:
        return {}


def remove_tags(s: str) -> str:
    return re.sub(r"<[^<]+?>", "", s)


def _sign_form_data(data: Dict[str, Any]) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "weixin": 1,
        "basic_v": 0,
        "f": "android",
        "v": APP_VERSION,
        "time": f"{int(time.time())}000",
    }
    base.update(data or {})

    # 删除空值，并按 key 排序
    filtered = {k: v for k, v in base.items() if v != ""}
    keys = sorted(filtered.keys())
    # 对齐 JS：String(v).replace(/\s+/, '') —— 去掉“第一段”空白（非全局）
    def _strip_first_ws(v: Any) -> str:
        return re.sub(r"\s+", "", str(v), count=1)

    sign_data = "&".join(f"{k}={_strip_first_ws(filtered[k])}" for k in keys)
    md5 = hashlib.md5()
    md5.update(f"{sign_data}&key={SIGN_KEY}".encode("utf-8"))
    sign = md5.hexdigest().upper()

    filtered["sign"] = sign
    return filtered


def request_api(
    url: str,
    *,
    method: str = "get",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[Dict[str, Any]] = None,
    sign: bool = True,
    parse_json_resp: bool = True,
    debug: bool = False,
    timeout: int = 15,
    retry: int = 2,
) -> Dict[str, Any]:
    """
    Python 版本的通用请求函数，返回结构与原 JS 版本尽量保持一致：
    { isSuccess: bool, response: str, data: Any }
    """
    method = method.lower() if method else "get"
    data = data or {}

    # 删除 undefined / None
    data = {k: v for k, v in data.items() if v is not None}

    if sign:
        data = _sign_form_data(data)

    session = requests.Session()
    last_error: Optional[Exception] = None

    # 优先尝试走代理，如果代理失败则自动切换为直连
    proxy_enabled = bool(PROXIES)

    for attempt in range(retry + 1):
        try:
            proxies = PROXIES if proxy_enabled else None

            if method == "get":
                resp = session.request(
                    "GET",
                    url,
                    params=data,
                    headers=headers,
                    timeout=timeout,
                    proxies=proxies,
                )
            else:
                resp = session.request(
                    method.upper(),
                    url,
                    data=data,
                    headers=headers,
                    timeout=timeout,
                    proxies=proxies,
                )

            body = resp.text
            parsed = parse_json(body) if parse_json_resp else body

            if debug:
                print("------------------------")
                print(url)
                print("------------------------")
                print("headers:", headers)
                print("method:", method)
                print("data:", data)
                print("------------------------")
                print(body if not parse_json_resp else parsed)
                print("------------------------")

            # 如果进到这里说明请求已成功返回，无论代理与否
            is_success = True if not parse_json_resp else str(parsed.get("error_code")) == "0"

            return {
                "isSuccess": is_success,
                "response": body if not parse_json_resp else _safe_json_dumps(parsed),
                "data": parsed,
            }
        except Exception as e:
            last_error = e

            # 如果当前还在使用代理且失败了，先关闭代理再重试一次直连
            if proxy_enabled:
                proxy_enabled = False
                if debug:
                    print("代理请求失败，切换为直连再重试一次。error:", repr(e))
                # 立即继续下一轮循环（直连），不算进 retry 次数
                continue

            if debug:
                print("------------------------")
                print(url)
                print("------------------------")
                print("headers:", headers)
                print("method:", method)
                print("data:", data)
                print("------------------------")
                print("error:", repr(e))
                print("------------------------")
            # 简单的重试间隔
            if attempt < retry:
                time.sleep(1)

    return {
        "isSuccess": False,
        "response": repr(last_error),
        "data": last_error,
    }


def _safe_json_dumps(obj: Any) -> str:
    try:
        import json

        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)


def _update_cookie(cookie: str, name: str, value: str) -> str:
    # 尽量复刻 JS 中的正则逻辑
    pattern = re.compile(rf"(^|;)\s*{re.escape(name)}=[^;]+;?", re.I)
    replacement = rf"\1{name}={requests.utils.quote(str(value))};"
    if pattern.search(cookie):
        return pattern.sub(replacement, cookie)
    # 如果原来没有该字段，则追加
    if not cookie.endswith(";"):
        cookie += ";"
    return cookie + f"{name}={requests.utils.quote(str(value))};"


def _build_cookies_from_smzdm_duihuan() -> Optional[List[str]]:
    """
    新方案：
    - 环境变量 smzdm_duihuan: cookies1#cookies2#cookies3  （整份网页 Cookie）
      形如：isg=...;MAWEBCUID=...;PSINO=7;PSTM=...;r_sort_type=score;sess=xxxx;...
    - 环境变量 smzdm_safe: 158306#368041#293154#704007#726824  （安全码列表）

    处理：
    - 先按 "#" 拆出多个 cookies
    - 再按 ";" 拆字段，取出 sess=xxx
    - 与 smzdm_safe 对应项拼接成 `sess=xxx;#安全码` 的形式
    - 返回列表，供兑换脚本等按「cookie#安全码」的老逻辑使用
    """
    raw_cookies = os.getenv("smzdm_duihuan", "") or ""
    raw_safe = os.getenv("smzdm_safe", "") or ""
    if not raw_cookies or not raw_safe:
        return None

    cookie_list = [c.strip() for c in raw_cookies.split("#") if c.strip()]
    safe_list = [s.strip() for s in raw_safe.split("#") if s.strip()]
    if not cookie_list:
        return None

    result: List[str] = []
    for idx, raw_cookie in enumerate(cookie_list):
        parts = [p.strip() for p in raw_cookie.split(";") if p.strip()]
        sess_val = ""
        for p in parts:
            if p.startswith("sess="):
                sess_val = p[len("sess=") :]
                break

        # 若未找到 sess 字段，则退回使用整份 Cookie
        if sess_val:
            cookie_part = f"sess={sess_val};"
        else:
            # 确保结尾有分号
            cookie_part = raw_cookie if raw_cookie.endswith(";") else raw_cookie + ";"

        safe_pass = safe_list[idx] if idx < len(safe_list) else ""
        if safe_pass:
            result.append(f"{cookie_part}#{safe_pass}")
        else:
            result.append(cookie_part)

    return result or None


def get_env_cookies_raw() -> Optional[list[str]]:
    """
    优先按新方案读取 smzdm_duihuan/smzdm_safe，其次回落到老的 SMZDM_COOKIE。

    新方案：
    - smzdm_duihuan: cookies1#cookies2#cookies3
    - smzdm_safe: 158306#368041#...
    - 返回形式：["sess=xxx1;#158306", "sess=xxx2;#368041", ...]

    旧方案：
    - 原始读取环境变量 SMZDM_COOKIE，不处理安全码。

    支持多账号格式：
    - cookie1
    - cookie1&cookie2
    - 按行分隔
    - cookie1#158306  （# 后面内容原样保留，给特殊任务用）
    """
    # 1. 优先尝试 smzdm_duihuan/smzdm_safe 新环境变量
    new_cookies = _build_cookies_from_smzdm_duihuan()
    if new_cookies:
        return new_cookies

    # 2. 回落到旧的 SMZDM_COOKIE
    raw = os.getenv("SMZDM_COOKIE", "") or ""
    if not raw:
        return None

    if "&" in raw:
        cookies = raw.split("&")
    elif "\n" in raw:
        cookies = raw.splitlines()
    else:
        cookies = [raw]

    cookies = [c.strip() for c in cookies if c.strip()]
    return cookies or None


def get_env_cookies() -> Optional[list[str]]:
    """
    普通任务用的 Cookie 列表。

    规则：
    - 忽略安全码：如果某一项形如 cookies#158306，则只返回 # 前面的 cookies 部分
    - 这样除了兑换脚本（单独用 get_env_cookies_raw 解析安全码），
      其他任务都不会把安全码当成 Cookie 一部分。
    """
    raw_list = get_env_cookies_raw()
    if not raw_list:
        return None

    def _strip_safe_pass(c: str) -> str:
        # 只取 # 之前部分
        return c.split("#", 1)[0].strip()

    cookies = [_strip_safe_pass(c) for c in raw_list]
    cookies = [c for c in cookies if c]
    return cookies or None


def random_decimal(min_second: float, max_second: float, precision: int = 1000) -> float:
    rand = random.uniform(min_second, max_second)
    return int(rand * precision) / precision


def wait(min_second: float, max_second: float) -> None:
    sec = random_decimal(min_second, max_second, 1000)
    print(f"等候 {min_second}-{max_second}({sec}) 秒")
    time.sleep(sec)


class SmzdmBot:
    """
    对应 JS 中的 SmzdmBot，封装 cookie、UA、公共请求头等。
    """

    def __init__(self, cookie: str) -> None:
        cookie = (cookie or "").strip()
        self.cookie = cookie

        m = re.search(r"sess=([^;]*)", cookie)
        self.token = m.group(1) if m else ""

        # 处理成 Android Cookie（尽量与 JS 一致）
        android_cookie = cookie.replace("iphone", "android").replace("iPhone", "Android")
        android_cookie = _update_cookie(android_cookie, "smzdm_version", APP_VERSION)
        android_cookie = _update_cookie(android_cookie, "device_smzdm_version", APP_VERSION)
        android_cookie = _update_cookie(android_cookie, "v", APP_VERSION)
        android_cookie = _update_cookie(
            android_cookie, "device_smzdm_version_code", APP_VERSION_REV
        )
        android_cookie = _update_cookie(android_cookie, "device_system_version", "10.0")
        android_cookie = _update_cookie(android_cookie, "apk_partner_name", "smzdm_download")
        android_cookie = _update_cookie(android_cookie, "partner_name", "smzdm_download")
        android_cookie = _update_cookie(android_cookie, "device_type", "Android")
        android_cookie = _update_cookie(android_cookie, "device_smzdm", "android")
        android_cookie = _update_cookie(android_cookie, "device_name", "Android")

        self.android_cookie = android_cookie

    def get_headers(self) -> Dict[str, str]:
        ua = DEFAULT_USER_AGENT_APP
        custom = os.getenv("SMZDM_USER_AGENT_APP")
        if custom:
            ua = RE_VERSION.sub(rf"\1{APP_VERSION}", custom)
            ua = RE_REV.sub(f"rv:{APP_VERSION_REV}", ua)

        return {
            "Accept": "*/*",
            "Accept-Language": "zh-Hans-CN;q=1",
            "Accept-Encoding": "gzip",
            "request_key": random_str(18),
            "User-Agent": ua,
            "Cookie": self.android_cookie,
        }

    def get_headers_for_web(self) -> Dict[str, str]:
        ua = DEFAULT_USER_AGENT_WEB
        custom = os.getenv("SMZDM_USER_AGENT_WEB")
        if custom:
            ua = RE_VERSION.sub(rf"\1{APP_VERSION}", custom)
            ua = RE_REV.sub(f"rv:{APP_VERSION_REV}", ua)

        return {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "Accept-Encoding": "gzip",
            "User-Agent": ua,
            "Cookie": self.android_cookie,
        }

    @staticmethod
    def get_one_by_random(items: list) -> Any:
        return random.choice(items)


__all__ = [
    "SmzdmBot",
    "request_api",
    "remove_tags",
    "parse_json",
    "get_env_cookies",
    "get_env_cookies_raw",
    "bark_notify",
    "wait",
]

