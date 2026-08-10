import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict
import json
import os

from smzdm_bot import get_env_cookies
from smzdm_db import init_db, save_gift_items

proxies = {
    "http": "socks5://admin:admin123@172.17.0.1:1080",
    "https": "socks5://admin:admin123@172.17.0.1:1080",
}


def h_html(cookie: str, out_file: str = "smzdm_response.html") -> str:
    url = "https://duihuan.smzdm.com/"

    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "max-age=0",
        "cookie": cookie,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    }

    try:
        response = requests.get(url, headers=headers, timeout=20, proxies=proxies)

        with open(out_file, "w", encoding="utf-8") as f:
            f.write(response.text)
        print(f"响应已保存到 {out_file}")

        return response.text

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        return ""


def parse_exchange_items(html_content: str) -> List[Dict]:
    """解析礼品兑换信息"""
    soup = BeautifulSoup(html_content, "html.parser")

    exchange_items = soup.find_all("li", class_="exchange-item")

    results = []

    for item in exchange_items:
        try:
            link_tag = item.find("a", class_="exchange-link")
            name = link_tag.text.strip() if link_tag else "未知商品"

            href_tag = item.find("a", class_="exchange-image")
            href = href_tag.get("href", "") if href_tag else ""
            full_url = f"https://duihuan.smzdm.com{href}" if href else ""

            price_div = item.find("div", class_="ticket-info-bottom")
            data_pre_p = price_div.get("data-pre-p", "") if price_div else ""

            price_span = price_div.find("span") if price_div else None
            price_text = price_span.text.strip() if price_span else ""

            info_top = item.find("div", class_="ticket-info-top")
            claimed = ""
            remaining = ""

            if info_top:
                spans = info_top.find_all("span")

                if spans and len(spans) > 0:
                    for node in info_top.contents:
                        if getattr(node, "name", None) == "span" and "已领" in str(node):
                            next_node = node.next_sibling
                            if next_node:
                                claimed = str(next_node).strip()
                                break

                if len(spans) > 1:
                    second_span = spans[1]
                    remaining_span = second_span.find_next(
                        "span", class_="ticket-info-red"
                    )
                    if remaining_span:
                        remaining = remaining_span.text.strip()

            results.append(
                {
                    "name": name,
                    "href": href,
                    "full_url": full_url,
                    "data_pre_p": data_pre_p,
                    "price_text": price_text,
                    "claimed": claimed,
                    "remaining": remaining,
                }
            )

        except Exception as e:
            print(f"解析错误: {e}")
            continue

    return results


def parse_all_items(html_content: str) -> Dict:
    """解析所有类型的商品信息"""
    soup = BeautifulSoup(html_content, "html.parser")

    results = {
        "coupons": [],
        "lucky_items": [],
        "exchange_items": [],
    }

    discount_items = soup.find_all("li", class_="ticket")
    for item in discount_items:
        try:
            title_tag = item.find("div", class_="ticket-title").find("a")
            name = title_tag.text.strip() if title_tag else ""
            href = title_tag.get("href", "") if title_tag else ""

            cost_div = item.find("div", class_="ticket-cost")
            price = cost_div.find("span").text.strip() if cost_div else ""
            price_unit = "金币" if cost_div else ""

            results["coupons"].append(
                {"name": name, "href": href, "price": f"{price}{price_unit}"}
            )
        except Exception:
            continue

    lucky_items = soup.find_all("li", class_="lucky-border")
    for item in lucky_items:
        try:
            title_tag = item.find("a", class_="title")
            name = title_tag.text.strip() if title_tag else ""

            data_div = item.find("div", class_="data")
            progress_data = data_div.text.strip() if data_div else ""

            if "/" in progress_data:
                current, total = progress_data.split("/")
                progress = {
                    "current": current.strip(),
                    "total": total.strip(),
                    "percentage": f"{int(current)/int(total)*100:.1f}%"
                    if current.isdigit() and total.isdigit()
                    else "0%",
                }
            else:
                progress = {"current": "0", "total": "0", "percentage": "0%"}

            results["lucky_items"].append({"name": name, "progress": progress})
        except Exception:
            continue

    results["exchange_items"] = parse_exchange_items(html_content)

    return results


def save_to_json(data: Dict, filename: str):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"数据已保存到 {filename}")


def save_to_csv(data: Dict, filename: str):
    import csv

    exchange_items = data.get("exchange_items", [])

    if not exchange_items:
        print("没有礼品兑换数据")
        return

    with open(filename, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["商品名称", "链接", "完整URL", "data-pre-p属性", "价格文本", "已领数量", "剩余数量"]
        )

        for item in exchange_items:
            writer.writerow(
                [
                    item["name"],
                    item["href"],
                    item["full_url"],
                    item["data_pre_p"],
                    item["price_text"],
                    item["claimed"],
                    item["remaining"],
                ]
            )

    print(f"CSV数据已保存到 {filename}")


def main():
    cookies = get_env_cookies()
    if not cookies:
        print("\n请先设置 SMZDM_COOKIE 环境变量")
        return

    init_db()

    all_data = None

    for idx, cookie in enumerate(cookies, start=1):
        if not cookie:
            continue

        print(f"\n开始使用第 {idx} 个 cookie 请求兑换首页...")
        html_content = h_html(cookie=cookie, out_file=f"smzdm_response_{idx}.html")
        if not html_content:
            print("本次未获取到 HTML，尝试下一个 cookie...")
            continue

        print("开始解析数据...")
        parsed = parse_all_items(html_content)

        exchange_items = (
            parsed.get("exchange_items", []) if isinstance(parsed, Dict) else []
        )
        if exchange_items:
            all_data = parsed
            print(
                f"已成功解析到 {len(exchange_items)} 个礼品兑换条目，停止尝试后续 cookie。"
            )
            break

        print("未解析到礼品兑换数据，尝试下一个 cookie...")

    if not all_data:
        print("\n所有 cookie 都未解析到礼品兑换数据。")
        return

    print("\n=== 礼品兑换信息 ===")
    for i, item in enumerate(all_data["exchange_items"], 1):
        print(f"\n商品 {i}:")
        print(f"  名称: {item['name']}")
        print(f"  链接: {item['href']}")
        print(f"  完整URL: {item['full_url']}")
        print(f"  data-pre-p: {item['data_pre_p']}")
        print(f"  价格: {item['price_text']}")
        print(f"  已领: {item['claimed']}")
        print(f"  剩余: {item['remaining']}")

    def _extract_gift_id_from_href(href: str) -> str:
        m = re.search(r"/d/(\d+)", href or "")
        return m.group(1) if m else ""

    gift_rows = []
    for item in all_data["exchange_items"]:
        gift_id = _extract_gift_id_from_href(item.get("href", ""))
        if not gift_id:
            continue

        data_pre_p = item.get("data_pre_p", "") or ""
        price_text = item.get("price_text", "") or ""

        cost_value = 0
        m_num = re.search(r"(\d+)", data_pre_p)
        if m_num:
            cost_value = int(m_num.group(1))
        else:
            m2 = re.search(r"(\d+)", price_text)
            cost_value = int(m2.group(1)) if m2 else 0

        if "金币" in data_pre_p or "金币" in price_text:
            cost_type = "gold"
        else:
            cost_type = "silver"

        claimed_raw = str(item.get("claimed") or "").strip()
        remaining_raw = str(item.get("remaining") or "").strip()
        claimed = int(claimed_raw) if claimed_raw.isdigit() else 0
        remaining = int(remaining_raw) if remaining_raw.isdigit() else 0

        gift_rows.append(
            {
                "gift_id": gift_id,
                "name": item.get("name", ""),
                "cost_value": cost_value,
                "cost_type": cost_type,
                "remaining": remaining,
                "claimed": claimed,
                "data_pre_p": data_pre_p,
                "price_text": price_text,
            }
        )

    if gift_rows:
        save_gift_items(gift_rows)
        print(f"\n已将 {len(gift_rows)} 条礼品兑换商品写入数据库。")

    print("\n=== 统计信息 ===")
    print(f"优惠券数量: {len(all_data['coupons'])}")
    print(f"幸运屋商品数量: {len(all_data['lucky_items'])}")
    print(f"礼品兑换数量: {len(all_data['exchange_items'])}")

    save_to_json(all_data, "smzdm_data.json")
    save_to_csv(all_data, "smzdm_exchange.csv")


if __name__ == "__main__":
    main()
