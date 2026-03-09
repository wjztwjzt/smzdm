"""
兑换礼品 + 获取「我的礼品」列表并解析审核状态/券码。

环境变量：
- SMZDM_COOKIE: 「cookies;en_safepass=123456;」这样的结构
  - 可配置多账号：用 & 分隔多个条目
  - 例：SMZDM_COOKIE="cookie1;en_safepass=111111;&cookie2;en_safepass=222222;"
- SMZDM_GIFT_ID: 要兑换的礼品 ID（默认 800626）
- SMZDM_GIFT_HTML_FILE: 若设置，从该文件读取 HTML（调试用，不请求网络）
- SMZDM_DEBUG_HTML: 设为 1 时，将请求到的 HTML 保存为 smzdm_gift_debug.html
"""

from __future__ import annotations

import os
import re
import json
from dataclasses import dataclass
from typing import List, Optional
import time
import requests

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment]




UA_PC = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
)


@dataclass
class GiftRecord:
    title: str
    url: str
    status: str  # 审核中 / 审核通过 ...
    date_text: str  # 刚刚 / 2024-08-27 ...
    secret: str  # 券码/密码（如果页面里有）
    gift_id: str


def _strip_to_html(text: str) -> str:
    """
    兼容你粘贴的那种：前面带 HTTP/1.1 200 OK 头 + chunk 长度。
    requests 正常拿到的是纯 HTML；如果前面有杂质，这里尽量裁切到 HTML 开头。
    """
    if not text:
        return ""
    m = re.search(r"(?is)(<!doctype\s+html|<html\b)", text)
    return text[m.start() :] if m else text


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
    try:
        resp = requests.post(
            url,
            headers=headers,
            data=data,
            timeout=20,
        )
        try:
            return resp.json()
        except Exception:
            return {"status_code": resp.status_code, "text": resp.text}
    except Exception as e:
        return {"isSuccess": False, "error": repr(e)}


def get_gift_page(cookie: str, page: int = 1) -> str:
    """
    GET 我的礼品页。第 1 页 /user/gift/，第 n 页 /user/gift/p{n}/。
    """
    if page <= 1:
        url = "https://zhiyou.smzdm.com/user/gift/"
    else:
        url = f"https://zhiyou.smzdm.com/user/gift/p{page}/"
    headers = {
        "Host": "zhiyou.smzdm.com",
        "Connection": "keep-alive",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": UA_PC,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
            "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
        ),
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1",
        "Sec-Fetch-Dest": "document",
        "Referer": "https://zhiyou.smzdm.com/user/coupon/",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7",
        "Cookie": cookie,
    }
    try:
        resp = requests.get(
            url,
            headers=headers,
            timeout=20,
        )
        return resp.text
    except Exception as e:
        return f"请求礼品页面失败: {e!r}"


def get_user_info(cookie: str) -> Optional[dict]:
    """
    使用账户 cookies 请求当前账户信息（昵称 / 金币 / 银币）。
    """
    url = (
        "https://zhiyou.smzdm.com/user/info/jsonp_get_current"
        "?with_avatar_ornament=1&callback=jQuery37105106474483029583_1773055514093"
        "&_=1773055514094"
    )
    headers = {
        "Host": "zhiyou.smzdm.com",
        "Connection": "keep-alive",
        "sec-ch-ua-platform": "Windows",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "sec-ch-ua": 'Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145',
        "sec-ch-ua-mobile": "?0",
        "Accept": "*/*",
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Dest": "script",
        "Referer": "https://duihuan.smzdm.com/",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Cookie": cookie,
    }

    try:
        resp = requests.get(url, headers=headers, timeout=20)
        text = resp.text
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            print("  未能在用户信息响应中找到 JSON 部分")
            return None
        data = json.loads(m.group(0))
        return data
    except Exception as e:
        print(f"  获取用户信息失败: {e!r}")
        return None


# 分页链接：/user/gift/p2/、p3/ 等
_RE_PAGE = re.compile(r"/user/gift/p(\d+)/", re.I)


def _parse_max_page(html: str) -> int:
    """从分页区解析最大页码，未找到则返回 1。"""
    raw = _strip_to_html(html)
    nums = [int(m.group(1)) for m in _RE_PAGE.finditer(raw)]
    return max(nums, default=1)


def get_all_gift_pages(cookie: str) -> tuple[List[GiftRecord], str]:
    """
    拉取所有分页的「我的礼品」，解析后合并为一条记录列表。
    返回 (记录列表, 第 1 页 HTML)，供调试保存用。
    """
    all_records: List[GiftRecord] = []
    page1 = get_gift_page(cookie, 1)
    if page1.startswith("请求礼品页面失败"):
        return all_records, page1

    first = parse_gift_records(page1)
    all_records.extend(first)
    max_page = _parse_max_page(page1)
    if max_page <= 1:
        return all_records, page1

    for p in range(2, max_page + 1):
        html = get_gift_page(cookie, p)
        if html.startswith("请求礼品页面失败"):
            break
        rec = parse_gift_records(html)
        all_records.extend(rec)
        if not rec:
            break
    return all_records, page1


def _extract_gift_id(url: str) -> str:
    """
    从 https://duihuan.smzdm.com/d/800626  或 /d/800626/ 提取 800626
    """
    m = re.search(r"/d/(\d+)", url or "")
    return m.group(1) if m else ""


def _clean_title(s: str) -> str:
    """去掉标题末尾的 " >"、" ›" 等（来自 <em>&gt;</em>）。"""
    if not s:
        return s
    return re.sub(r"\s*[>›]\s*$", "", s).strip()


# 正则回退：匹配 href 里 duihuan.smzdm.com/d/ 数字
_RE_GIFT_HREF = re.compile(
    r'href\s*=\s*["\'](https?://duihuan\.smzdm\.com/d/(\d+)[^"\']*)["\']',
    re.I,
)


def _parse_gift_records_regex(html: str) -> List[GiftRecord]:
    """
    BS4 解析到 0 条时，用正则扫描整页 href，提取礼品 ID / URL；
    在链接前取最后一个 scoreLeft，链接后取第一个 scoreUse。
    """
    raw = _strip_to_html(html)
    if not raw:
        return []

    pat_left = re.compile(r'<div\s+class="[^"]*scoreLeft[^"]*"[^>]*>([^<]*)</div>', re.I)
    pat_use = re.compile(r'<div\s+class="[^"]*scoreUse[^"]*"[^>]*>([^<]*)</div>', re.I)
    pat_title = re.compile(
        r'<a\s+href\s*=\s*["\'][^"\']*duihuan\.smzdm\.com/d/\d+[^"\']*["\'][^>]*>([^<]+)',
        re.I,
    )
    pat_secret = re.compile(
        r'<div\s+class="[^"]*subNoticeYellow[^"]*"[^>]*>([^<]*)</div>',
        re.I,
    )
    records: List[GiftRecord] = []

    for m in _RE_GIFT_HREF.finditer(raw):
        full_url = (m.group(1) or "").strip()
        gid = m.group(2) or ""
        if not gid:
            continue
        before = raw[max(0, m.start() - 800) : m.start()]
        after = raw[m.end() : m.end() + 600]
        lefts = pat_left.findall(before)
        date_text = (lefts[-1] or "").strip() if lefts else ""
        uses = pat_use.findall(after)
        status = (uses[0] or "").strip() if uses else ""
        tm = pat_title.search(before + raw[m.start() : m.end() + 200])
        title = (tm.group(1) or "").strip() if tm else f"礼品 {gid}"
        title = _clean_title(re.sub(r"<[^>]+>", " ", title).strip() or f"礼品 {gid}")
        secrets = pat_secret.findall(before + after)
        secret = (secrets[0] or "").replace("\xa0", " ").strip() if secrets else ""
        records.append(
            GiftRecord(
                title=title,
                url=full_url,
                status=status,
                date_text=date_text,
                secret=secret,
                gift_id=gid,
            )
        )
    return records


def parse_gift_records(html: str) -> List[GiftRecord]:
    """
    解析「我的礼品」页 HTML。先 BS4 find_all/find；若 0 条则用正则回退。
    """
    html = _strip_to_html(html)
    if not html:
        return []

    if BeautifulSoup is None:
        raise RuntimeError("缺少依赖 beautifulsoup4：请先 pip install beautifulsoup4")

    soup = BeautifulSoup(html, "html.parser")
    # 用正则匹配 class，兼容多 class、空格等
    rows = soup.find_all("div", class_=re.compile(r"infoScoreListGrey", re.I))
    records: List[GiftRecord] = []

    for item in rows:
        try:
            date_div = item.find("div", class_=re.compile(r"scoreLeft", re.I))
            date_text = date_div.get_text(strip=True) if date_div else ""

            a = None
            title_span = item.find("span", class_=re.compile(r"titleArrow", re.I))
            if title_span:
                a = title_span.find("a")
            if not a:
                for tag in item.find_all("a", href=True):
                    href = tag.get("href") or ""
                    if re.search(r"duihuan\.smzdm\.com/d/\d+", href):
                        a = tag
                        break
            title = _clean_title(a.get_text(" ", strip=True) if a else "")
            url = (a.get("href") or "").strip() if a else ""

            status_div = item.find("div", class_=re.compile(r"scoreUse", re.I))
            status = status_div.get_text(strip=True) if status_div else ""

            secret_div = item.find("div", class_=re.compile(r"subNoticeYellow", re.I))
            secret = ""
            if secret_div:
                secret = (
                    secret_div.get_text(" ", strip=True).replace("\xa0", " ").strip()
                )

            gift_id = _extract_gift_id(url)
            if not gift_id:
                continue

            records.append(
                GiftRecord(
                    title=title or f"礼品 {gift_id}",
                    url=url,
                    status=status,
                    date_text=date_text,
                    secret=secret,
                    gift_id=gift_id,
                )
            )
        except Exception:
            continue

    if not records:
        records = _parse_gift_records_regex(html)

    return records


def pick_record_by_id(records: List[GiftRecord], gift_id: str) -> Optional[GiftRecord]:
    gift_id = (gift_id or "").strip()
    if not gift_id:
        return None
    for r in records:
        if r.gift_id == gift_id:
            return r
    return None


def _run_one(
    page_html: str,
    gift_id: str,
    *,
    from_file: bool = False,
) -> int:
    """解析 HTML、打印结果。返回解析到的记录数。"""
    records = parse_gift_records(page_html)
    return _run_one_from_records(
        records, gift_id, page_html=page_html, from_file=from_file, merged_pages=False
    )


def _run_one_from_records(
    records: List[GiftRecord],
    gift_id: str,
    *,
    page_html: Optional[str] = None,
    from_file: bool = False,
    merged_pages: bool = False,
) -> int:
    """根据已解析的记录打印结果；若无记录且提供 page_html 则打调试信息。"""
    suffix = "（已合并全部分页）" if merged_pages else ""
    print(f"解析到礼品记录条数：{len(records)}{suffix}")

    if not records and page_html:
        clean = _strip_to_html(page_html)
        has_block = "infoScoreListGrey" in clean
        has_gift = "duihuan.smzdm.com/d/" in clean
        print(
            f"  [调试] HTML 长度 {len(clean)} | "
            f"含 infoScoreListGrey: {has_block} | 含 duihuan.smzdm.com/d/: {has_gift}"
        )
        if not has_gift:
            msg = "疑似非「我的礼品」页（如登录页）"
            if not from_file:
                msg += "，请检查 cookie 或设置 SMZDM_GIFT_HTML_FILE 用本地 HTML 测试"
            print(f"  [调试] {msg}。")

    hit = pick_record_by_id(records, gift_id)
    if hit:
        print("目标礼品：")
        print("  标题：", hit.title)
        print("  链接：", hit.url)
        print("  状态：", hit.status)
        print("  时间：", hit.date_text)
        print("  券码：", hit.secret or "(页面未展示/暂无)")
    else:
        print("未在列表中找到目标礼品 ID，预览前 5 条：")
        for r in records[:5]:
            extra = f" | {r.secret}" if r.secret else ""
            print(f"- {r.date_text} | {r.status} | {r.gift_id} | {r.title}{extra}")
    return len(records)


def _parse_cookie_and_safe_pass(entry: str) -> tuple[str, str]:
    """
    解析单个账号字符串：
    前半部分是 cookies，后面跟着 ;en_safepass=xxxx;，需要拆出安全码。
    """
    entry = (entry or "").strip()
    if not entry:
        return "", ""
    # 取最后一个 ;en_safepass=，避免中间意外包含相同片段
    marker = ";en_safepass="
    idx = entry.rfind(marker)
    if idx == -1:
        return entry, ""
    # 安全码在 marker 之后、下一个分号之前
    rest = entry[idx + len(marker) :]
    safe_pass = rest.split(";", 1)[0].strip()
    cookie = entry[:idx].rstrip(" ;")
    return cookie, safe_pass


def main() -> None:
    SMZDM_COOKIE = os.getenv("SMZDM_COOKIE")
    if not SMZDM_COOKIE:
        print("未设置 SMZDM_COOKIE 环境变量")
        return

    # 多账号使用 & 分割
    raw_accounts = [c for c in SMZDM_COOKIE.split("&") if c.strip()]

    for idx, raw in enumerate(raw_accounts, start=1):
        print(f"开始第{idx}个账号：")
        cookie, safe_pass = _parse_cookie_and_safe_pass(raw)
        if not cookie:
            print("  本账号 cookie 为空，跳过")
            continue

        # 第一步：查询账户信息（昵称 / 金币 / 银币）
        user_info = get_user_info(cookie)
        if not user_info:
            print("  获取账户信息失败，跳过该账号")
            print("-" * 50)
            continue

        nickname = user_info.get("nickname")
        gold = user_info.get("gold")
        silver = user_info.get("silver")
        print(f"  昵称: {nickname}")
        print(f"  金币: {gold}")
        print(f"  银币: {silver}")

        # 第二步：根据银币决定是否尝试兑换
        try:
            silver_val = int(silver) if silver is not None else 0
        except (TypeError, ValueError):
            silver_val = 0

        gift_id = os.getenv("SMZDM_GIFT_ID", "800626")

        if silver_val < 600:
            print("  银币不足 600，不尝试兑换。")
        else:
            print(f"  银币充足，尝试兑换礼品 {gift_id} ...")
            resp = post_exchange(cookie, safe_pass, gift_id)
            print(f"  兑换接口返回: {resp}")

        time.sleep(2)

        # 第三步：查询「我的礼品」第一页，并解析卷码信息（只展示前三条）
        page1 = get_gift_page(cookie, 1)

        if page1.startswith("请求礼品页面失败"):
            print(f"  请求失败: {page1}")
            print("-" * 50)
            continue

        records = parse_gift_records(page1)

        if records:
            print(f"  找到 {len(records)} 条礼品记录（仅展示前 3 条）:")
            for i, record in enumerate(records[:3], 1):
                output = (
                    f"    {i}. {record.date_text} | {record.status} | {record.title}"
                )
                if "审核通过" in record.status and record.secret:
                    output += f" | 券码: {record.secret}"
                print(output)
        else:
            print("  未找到礼品记录")

        print("-" * 50)
if __name__ == "__main__":
    main()
