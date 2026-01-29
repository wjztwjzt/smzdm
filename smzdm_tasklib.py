import json
import os
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from smzdm_bot import SmzdmBot, request_api, remove_tags, wait


class SmzdmTaskBot(SmzdmBot):
    """
    Python 版任务基类，对齐 library_task.js（核心接口与任务动作）。

    说明：
    - 原 JS 里通过 this.$env.log 输出；这里统一用 print。
    - 所有方法尽量保持原行为（含随机等待、touchstone_event 等）。
    """

    def log(self, msg: str = "") -> None:
        print(msg)

    def get_task_notify_message(self, is_success: bool, task: Dict[str, Any]) -> str:
        name = task.get("task_name", "")
        return f"{'🟢' if is_success else '❌'}完成[{name}]任务{'成功' if is_success else '失败！请查看日志'}\n"

    def do_tasks(self, tasks: List[Dict[str, Any]]) -> str:
        notify_msg = ""
        for task in tasks:
            status = str(task.get("task_status", ""))
            event_type = task.get("task_event_type", "")

            # 待领取任务
            if status == "3":
                self.log(f"领取[{task.get('task_name','')}]奖励:")
                result = self.receive_reward(str(task.get("task_id", "")))
                notify_msg += (
                    f"{'🟢' if result.get('isSuccess') else '❌'}领取[{task.get('task_name','')}]奖励"
                    f"{'成功' if result.get('isSuccess') else '失败！请查看日志'}\n"
                )
                wait(5, 15)
                continue

            # 未完成任务
            if status != "2":
                continue

            if event_type == "interactive.view.article":
                is_success = self.do_view_task(task).get("isSuccess", False)
                notify_msg += self.get_task_notify_message(is_success, task)
                wait(5, 15)
            elif event_type == "interactive.share":
                is_success = self.do_share_task(task).get("isSuccess", False)
                notify_msg += self.get_task_notify_message(is_success, task)
                wait(5, 15)
            elif event_type == "guide.crowd":
                res = self.do_crowd_task(task)
                if res.get("code") != 99:
                    notify_msg += self.get_task_notify_message(res.get("isSuccess", False), task)
                wait(5, 15)
            elif event_type == "interactive.follow.user":
                is_success = self.do_follow_user_task(task).get("isSuccess", False)
                notify_msg += self.get_task_notify_message(is_success, task)
                wait(5, 15)
            elif event_type == "interactive.follow.tag":
                is_success = self.do_follow_tag_task(task).get("isSuccess", False)
                notify_msg += self.get_task_notify_message(is_success, task)
                wait(5, 15)
            elif event_type == "interactive.follow.brand":
                is_success = self.do_follow_brand_task(task).get("isSuccess", False)
                notify_msg += self.get_task_notify_message(is_success, task)
                wait(5, 15)
            elif event_type == "interactive.favorite":
                is_success = self.do_favorite_task(task).get("isSuccess", False)
                notify_msg += self.get_task_notify_message(is_success, task)
                wait(5, 15)
            elif event_type == "interactive.rating":
                is_success = self.do_rating_task(task).get("isSuccess", False)
                notify_msg += self.get_task_notify_message(is_success, task)
                wait(5, 15)
            elif event_type == "interactive.comment":
                comment = os.getenv("SMZDM_COMMENT", "")
                if comment and len(str(comment)) > 10:
                    is_success = self.do_comment_task(task).get("isSuccess", False)
                    notify_msg += self.get_task_notify_message(is_success, task)
                    wait(5, 15)
                else:
                    self.log("🟡请设置 SMZDM_COMMENT 环境变量后才能做评论任务！")

        return notify_msg

    # ---------------------- 任务动作：评论 ----------------------
    def do_comment_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        self.log(f"开始任务: {task.get('task_name','')}")
        articles = self.get_article_list(20)
        if len(articles) < 1:
            return {"isSuccess": False}

        article = random.choice(articles)
        wait(3, 10)

        res = self.submit_comment(
            article_id=str(article.get("article_id", "")),
            channel_id=str(article.get("article_channel_id", "")),
            content=os.getenv("SMZDM_COMMENT", ""),
        )
        if not res.get("isSuccess"):
            return {"isSuccess": False}

        self.log("删除评论")
        wait(20, 30)
        comment_id = str(((res.get("data") or {}).get("data") or {}).get("comment_ID", ""))
        rm = self.remove_comment(comment_id)
        if not rm.get("isSuccess"):
            self.log("再试一次")
            wait(10, 20)
            self.remove_comment(comment_id)

        self.log("领取奖励")
        wait(5, 15)
        return self.receive_reward(str(task.get("task_id", "")))

    # ---------------------- 任务动作：点赞/点值 ----------------------
    def do_rating_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        self.log(f"开始任务: {task.get('task_name','')}")

        redirect = task.get("task_redirect_url") or {}
        link_val = str(redirect.get("link_val", ""))
        link_type = redirect.get("link_type", "")
        link = str(redirect.get("link", ""))
        desc = str(task.get("task_description", ""))

        article: Optional[Dict[str, Any]] = None

        if ("任意" in desc) or link_val == "0" or not link_val:
            articles = self.get_article_list(20)
            if len(articles) < 1:
                return {"isSuccess": False}
            article = self.get_one_by_random(articles)
        elif link_type == "lanmu":
            articles = self.get_article_list_from_lanmu(link_val, 20)
            if len(articles) < 1:
                return {"isSuccess": False}
            article = self.get_one_by_random(articles)
        elif link and link_val:
            channel_id = self.get_article_channel_id_for_testing(link)
            if not channel_id:
                return {"isSuccess": False}
            article = {"article_id": link_val, "article_channel_id": channel_id}
        else:
            self.log("尚未支持")
            return {"isSuccess": False}

        wait(3, 10)

        aid = str(article.get("article_id", ""))
        cid = str(article.get("article_channel_id", ""))

        # JS 里通过 article.article_price 判断点值/点赞；这里兼容字段缺失
        if article.get("article_price"):
            self.rating(method="worth_cancel", aid=aid, channel_id=cid, wtype=3)
            wait(3, 10)
            self.rating(method="worth_create", aid=aid, channel_id=cid, wtype=1)
            wait(3, 10)
            self.rating(method="worth_cancel", aid=aid, channel_id=cid, wtype=3)
        else:
            self.rating(method="like_cancel", aid=aid, channel_id=cid, wtype=None)
            wait(3, 10)
            self.rating(method="like_create", aid=aid, channel_id=cid, wtype=None)
            wait(3, 10)
            self.rating(method="like_cancel", aid=aid, channel_id=cid, wtype=None)
            wait(3, 10)
            self.rating(method="like_create", aid=aid, channel_id=cid, wtype=None)
            wait(3, 10)
            self.rating(method="like_cancel", aid=aid, channel_id=cid, wtype=None)

        self.log("领取奖励")
        wait(5, 15)
        return self.receive_reward(str(task.get("task_id", "")))

    # ---------------------- 任务动作：收藏 ----------------------
    def do_favorite_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        self.log(f"开始任务: {task.get('task_name','')}")
        redirect = task.get("task_redirect_url") or {}

        article_id = ""
        channel_id = ""

        if redirect.get("link_type") == "lanmu":
            articles = self.get_article_list_from_lanmu(str(redirect.get("link_val", "")), 20)
            if len(articles) < 1:
                return {"isSuccess": False}
            a = self.get_one_by_random(articles)
            article_id = str(a.get("article_id", ""))
            channel_id = str(a.get("article_channel_id", ""))
        elif redirect.get("link_type") == "tag":
            articles = self.get_article_list_from_tag(
                str(redirect.get("link_val", "")),
                str(redirect.get("link_title", "")),
                20,
            )
            if len(articles) < 1:
                return {"isSuccess": False}
            a = self.get_one_by_random(articles)
            article_id = str(a.get("article_id", ""))
            channel_id = str(a.get("article_channel_id", ""))
        elif str(redirect.get("link_val", "")) == "0" or not redirect.get("link_val"):
            articles = self.get_article_list(20)
            if len(articles) < 1:
                return {"isSuccess": False}
            a = self.get_one_by_random(articles)
            article_id = str(a.get("article_id", ""))
            channel_id = str(a.get("article_channel_id", ""))
        else:
            article_id = str(redirect.get("link_val", ""))
            detail = self.get_article_detail(article_id)
            if not detail:
                return {"isSuccess": False}
            channel_id = str(detail.get("channel_id", ""))

        wait(3, 10)
        self.favorite(method="destroy", aid=article_id, channel_id=channel_id)
        wait(3, 10)
        self.favorite(method="create", aid=article_id, channel_id=channel_id)
        wait(3, 10)
        self.favorite(method="destroy", aid=article_id, channel_id=channel_id)

        self.log("领取奖励")
        wait(5, 15)
        return self.receive_reward(str(task.get("task_id", "")))

    # ---------------------- 任务动作：关注用户 ----------------------
    def do_follow_user_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        self.log(f"开始任务: {task.get('task_name','')}")
        user = self.get_user_by_random()
        if not user:
            return {"isSuccess": False}

        wait(3, 10)
        total = int(task.get("task_even_num", 0)) - int(task.get("task_finished_num", 0))
        total = max(total, 0)
        keyword = str(user.get("keyword", ""))
        is_follow = str(user.get("is_follow", "0"))

        for _ in range(total):
            if is_follow == "1":
                self.follow(method="destroy", ftype="user", keyword=keyword, keyword_id=None)
                wait(3, 10)
            self.follow(method="create", ftype="user", keyword=keyword, keyword_id=None)
            wait(3, 10)
            if is_follow == "0":
                self.follow(method="destroy", ftype="user", keyword=keyword, keyword_id=None)
            wait(3, 10)

        self.log("领取奖励")
        wait(5, 15)
        return self.receive_reward(str(task.get("task_id", "")))

    # ---------------------- 任务动作：关注栏目 ----------------------
    def do_follow_tag_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        self.log(f"开始任务: {task.get('task_name','')}")
        redirect = task.get("task_redirect_url") or {}
        lanmu_id = str(redirect.get("link_val", ""))

        if lanmu_id == "0":
            tag = self.get_tag_by_random()
            if not tag:
                return {"isSuccess": False}
            lanmu_id = str(tag.get("lanmu_id", ""))
            wait(3, 10)

        tag_detail = self.get_tag_detail(lanmu_id)
        if not tag_detail or not tag_detail.get("lanmu_id"):
            self.log("获取栏目信息失败！")
            return {"isSuccess": False}

        keyword_id = str(tag_detail.get("lanmu_id", ""))
        keyword = str(((tag_detail.get("lanmu_info") or {}).get("lanmu_name", "")))

        wait(3, 10)
        self.follow(method="destroy", ftype="tag", keyword=keyword, keyword_id=keyword_id)
        wait(3, 10)
        self.follow(method="create", ftype="tag", keyword=keyword, keyword_id=keyword_id)
        wait(3, 10)
        self.follow(method="destroy", ftype="tag", keyword=keyword, keyword_id=keyword_id)

        self.log("领取奖励")
        wait(5, 15)
        return self.receive_reward(str(task.get("task_id", "")))

    # ---------------------- 任务动作：关注品牌 ----------------------
    def do_follow_brand_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        self.log(f"开始任务: {task.get('task_name','')}")
        redirect = task.get("task_redirect_url") or {}
        brand_id = str(redirect.get("link_val", ""))

        brand = self.get_brand_detail(brand_id)
        if not brand or not brand.get("id"):
            return {"isSuccess": False}

        bid = str(brand.get("id"))
        title = str(brand.get("title", ""))

        wait(3, 10)
        self.follow_brand(method="dingyue_lanmu_del", keyword_id=bid, keyword=title)
        wait(3, 10)
        self.follow_brand(method="dingyue_lanmu_add", keyword_id=bid, keyword=title)
        wait(3, 10)
        self.follow_brand(method="dingyue_lanmu_del", keyword_id=bid, keyword=title)

        self.log("领取奖励")
        wait(5, 15)
        return self.receive_reward(str(task.get("task_id", "")))

    # ---------------------- 任务动作：抽奖（幸运屋） ----------------------
    def do_crowd_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        self.log(f"开始任务: {task.get('task_name','')}")
        res = self.get_crowd("免费", 0)
        if not res.get("isSuccess"):
            if os.getenv("SMZDM_CROWD_SILVER_5") == "yes":
                res = self.get_crowd("5碎银子", 5)
                if not res.get("isSuccess"):
                    return {"isSuccess": False, "code": 99}
            else:
                self.log("🟡请设置 SMZDM_CROWD_SILVER_5 环境变量值为 yes 后才能进行5碎银子抽奖！")
                return {"isSuccess": False, "code": 99}

        wait(5, 15)
        joined = self.join_crowd(str(res.get("data", "")))
        if not joined.get("isSuccess"):
            return {"isSuccess": False}

        self.log("领取奖励")
        wait(5, 15)
        return self.receive_reward(str(task.get("task_id", "")))

    # ---------------------- 任务动作：分享 ----------------------
    def do_share_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        self.log(f"开始任务: {task.get('task_name','')}")
        articles: List[Dict[str, Any]] = []
        if str(task.get("article_id", "")) == "0":
            need = int(task.get("task_even_num", 0)) - int(task.get("task_finished_num", 0))
            need = max(need, 0)
            articles = self.get_article_list(need)
            wait(3, 10)
        else:
            articles = [
                {"article_id": task.get("article_id"), "article_channel_id": task.get("channel_id")}
            ]

        redirect = task.get("task_redirect_url") or {}
        link_type = redirect.get("link_type", "")
        scheme_url = str(redirect.get("scheme_url", ""))

        for idx, article in enumerate(articles):
            self.log(f"开始分享第 {idx + 1} 篇文章...")
            aid = str(article.get("article_id", ""))
            cid = str(article.get("article_channel_id", ""))

            if link_type != "other":
                if re.search(r"detail_haojia", scheme_url, re.I):
                    self.get_haojia_detail(aid)
                else:
                    self.get_article_detail(aid)
                wait(8, 20)

            self.share_article_done(aid, cid)
            self.share_daily_reward(cid)
            self.share_callback(aid, cid)
            wait(5, 15)

        self.log("领取奖励")
        wait(3, 10)
        return self.receive_reward(str(task.get("task_id", "")))

    # ---------------------- 任务动作：浏览文章 ----------------------
    def do_view_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        self.log(f"开始任务: {task.get('task_name','')}")
        articles: List[Dict[str, Any]] = []
        is_read = True

        if str(task.get("article_id", "")) == "0":
            need = int(task.get("task_even_num", 0)) - int(task.get("task_finished_num", 0))
            need = max(need, 0)
            articles = self.get_article_list(need)
            wait(3, 10)
        else:
            need = int(task.get("task_even_num", 0)) - int(task.get("task_finished_num", 0))
            need = max(need, 0)
            for _ in range(need):
                articles.append({"article_id": task.get("article_id"), "article_channel_id": task.get("channel_id")})
            redirect = task.get("task_redirect_url") or {}
            is_read = str(redirect.get("link_val", "")) != ""

        redirect = task.get("task_redirect_url") or {}
        scheme_url = str(redirect.get("scheme_url", ""))

        for idx, article in enumerate(articles):
            self.log(f"开始阅读第 {idx + 1} 篇文章...")
            aid = str(article.get("article_id", ""))
            cid = str(article.get("article_channel_id", ""))

            if is_read:
                if re.search(r"detail_haojia", scheme_url, re.I):
                    self.get_haojia_detail(aid)
                else:
                    self.get_article_detail(aid)

            self.log("模拟阅读文章")
            wait(20, 50)

            resp = request_api(
                "https://user-api.smzdm.com/task/event_view_article_sync",
                method="post",
                headers=self.get_headers(),
                data={"article_id": aid, "channel_id": cid, "task_id": str(task.get("task_id", ""))},
            )
            if resp["isSuccess"]:
                self.log("完成阅读成功。")
            else:
                self.log(f"完成阅读失败！{resp['response']}")
            wait(5, 15)

        self.log("领取奖励")
        wait(3, 10)
        return self.receive_reward(str(task.get("task_id", "")))

    # ---------------------- API：关注/取关 ----------------------
    def follow(self, *, method: str, ftype: str, keyword: str, keyword_id: Optional[str]) -> Dict[str, Any]:
        touchstone = ""
        if ftype == "user":
            touchstone = self.get_touchstone_event(
                {
                    "event_value": {"cid": "null", "is_detail": False, "p": "1"},
                    "sourceMode": "我的_我的任务页",
                    "sourcePage": "Android/关注/达人/爆料榜",
                    "upperLevel_url": "关注/达人/推荐/",
                }
            )
        elif ftype == "tag":
            touchstone = self.get_touchstone_event(
                {
                    "event_value": {"cid": "null", "is_detail": False},
                    "sourceMode": "栏目页",
                    "sourcePage": f"Android/栏目页/{keyword}/{keyword_id}/",
                    "source_page_type_id": str(keyword_id),
                    "upperLevel_url": "个人中心/赚奖励/",
                    "source_area": {"lanmu_id": str(keyword_id), "prev_source_scence": "我的_我的任务页"},
                }
            )

        resp = request_api(
            f"https://dingyue-api.smzdm.com/dingyue/{method}",
            method="post",
            headers=self.get_headers(),
            data={
                "touchstone_event": touchstone,
                "refer": "",
                "keyword_id": keyword_id,
                "keyword": keyword,
                "type": ftype,
            },
        )

        if resp["isSuccess"]:
            self.log(f"{method} 关注成功: {keyword}")
        else:
            self.log(f"{method} 关注失败！{resp['response']}")
        return {"isSuccess": resp["isSuccess"], "response": resp["response"]}

    # ---------------------- API：随机用户 ----------------------
    def get_user_by_random(self) -> Optional[Dict[str, Any]]:
        resp = request_api(
            "https://dingyue-api.smzdm.com/tuijian/search_result",
            method="post",
            headers=self.get_headers(),
            data={"nav_id": 0, "page": 1, "type": "user", "time_code": ""},
        )
        if resp["isSuccess"]:
            rows = ((resp["data"].get("data") or {}).get("rows") or [])
            return random.choice(rows) if rows else None
        self.log(f"获取用户列表失败！{resp['response']}")
        return None

    # ---------------------- API：参加抽奖 ----------------------
    def join_crowd(self, crowd_id: str) -> Dict[str, Any]:
        resp = request_api(
            "https://zhiyou.m.smzdm.com/user/crowd/ajax_participate",
            method="post",
            sign=False,
            headers={
                **self.get_headers_for_web(),
                "Origin": "https://zhiyou.m.smzdm.com",
                "Referer": f"https://zhiyou.m.smzdm.com/user/crowd/p/{crowd_id}/",
            },
            data={
                "crowd_id": crowd_id,
                "sourcePage": f"https://zhiyou.m.smzdm.com/user/crowd/p/{crowd_id}/",
                "client_type": "android",
                "sourceRoot": "个人中心",
                "sourceMode": "幸运屋抽奖",
                "price_id": 1,
            },
        )
        if resp["isSuccess"]:
            msg = remove_tags(((resp["data"].get("data") or {}).get("msg") or ""))
            self.log(msg)
        else:
            self.log(f"参加免费抽奖失败: {resp['response']}")
        return {"isSuccess": resp["isSuccess"], "response": resp["response"]}

    # ---------------------- API：获取抽奖信息（抓 HTML） ----------------------
    def get_crowd(self, name: str, price: int) -> Dict[str, Any]:
        resp = request_api(
            "https://zhiyou.smzdm.com/user/crowd/",
            method="get",
            sign=False,
            parse_json_resp=False,
            headers=self.get_headers_for_web(),
        )
        if not resp["isSuccess"]:
            self.log(f"获取{name}抽奖失败: {resp['response']}")
            return {"isSuccess": False}

        html = resp["data"]
        pattern = re.compile(
            rf'<button\s+([^>]+?)>\s+?<div\s+[^>]+?>\s*{re.escape(name)}(?:抽奖)?\s*</div>\s+<span\s+class="reduceNumber">-{price}</span>[\s\S]+?</button>',
            re.I,
        )
        crowds = pattern.findall(html or "")
        if len(crowds) < 1:
            self.log(f"未找到{name}抽奖")
            return {"isSuccess": False}

        crowd = None
        if price > 0 and os.getenv("SMZDM_CROWD_KEYWORD"):
            keyword = os.getenv("SMZDM_CROWD_KEYWORD", "")
            for item in crowds:
                m = re.search(r'data-title="([^"]+)"', item, re.I)
                if m and keyword in m.group(1):
                    crowd = item
                    break
            if not crowd:
                self.log("未找到符合关键词的抽奖，执行随机选取")
                crowd = random.choice(crowds)
        else:
            crowd = random.choice(crowds)

        m2 = re.search(r'data-crowd_id="(\d+)"', crowd, re.I)
        if m2:
            cid = m2.group(1)
            self.log(f"{name}抽奖ID: {cid}")
            return {"isSuccess": True, "data": cid}
        self.log(f"未找到{name}抽奖ID")
        return {"isSuccess": False}

    # ---------------------- API：分享相关 ----------------------
    def share_article_done(self, article_id: str, channel_id: str) -> Dict[str, Any]:
        resp = request_api(
            "https://user-api.smzdm.com/share/complete_share_rule",
            method="post",
            headers=self.get_headers(),
            data={"token": self.token, "article_id": article_id, "channel_id": channel_id, "tag_name": "gerenzhongxin"},
        )
        if resp["isSuccess"]:
            self.log("完成分享成功。")
            return {"isSuccess": True, "msg": "完成分享成功。"}
        self.log(f"完成分享失败！{resp['response']}")
        return {"isSuccess": False, "msg": "完成分享失败！"}

    def share_callback(self, article_id: str, channel_id: str) -> Dict[str, Any]:
        touchstone = self.get_touchstone_event(
            {
                "event_value": {"aid": article_id, "cid": channel_id, "is_detail": True, "pid": "无"},
                "sourceMode": "排行榜_社区_好文精选",
                "sourcePage": f"Android/长图文/P/{article_id}/",
                "upperLevel_url": "排行榜/社区/好文精选/文章_24H/",
            }
        )
        resp = request_api(
            "https://user-api.smzdm.com/share/callback",
            method="post",
            headers=self.get_headers(),
            data={
                "token": self.token,
                "article_id": article_id,
                "channel_id": channel_id,
                "touchstone_event": touchstone,
            },
        )
        if resp["isSuccess"]:
            self.log("分享回调完成。")
            return {"isSuccess": True, "msg": ""}
        self.log(f"分享回调失败！{resp['response']}")
        return {"isSuccess": False, "msg": "分享回调失败！"}

    def share_daily_reward(self, channel_id: str) -> Dict[str, Any]:
        resp = request_api(
            "https://user-api.smzdm.com/share/daily_reward",
            method="post",
            headers=self.get_headers(),
            data={"token": self.token, "channel_id": channel_id},
        )
        if resp["isSuccess"]:
            desc = ((resp["data"].get("data") or {}).get("reward_desc") or "")
            self.log(desc)
            return {"isSuccess": True, "msg": desc}
        data = resp.get("data")
        if isinstance(data, dict) and data.get("error_msg"):
            self.log(str(data.get("error_msg")))
            return {"isSuccess": False, "msg": str(data.get("error_msg"))}
        self.log(f"分享每日奖励请求失败！{resp['response']}")
        return {"isSuccess": False, "msg": "分享每日奖励请求失败！"}

    # ---------------------- API：文章/栏目/品牌 ----------------------
    def get_article_list(self, num: int = 1) -> List[Dict[str, Any]]:
        resp = request_api(
            "https://article-api.smzdm.com/ranking_list/articles",
            method="get",
            headers=self.get_headers(),
            data={
                "offset": 0,
                "channel_id": 76,
                "tab": 2,
                "order": 0,
                "limit": 20,
                "exclude_article_ids": "",
                "stream": "a",
                "ab_code": "b",
            },
        )
        if resp["isSuccess"]:
            rows = ((resp["data"].get("data") or {}).get("rows") or [])
            return rows[: max(num, 0)]
        self.log(f"获取文章列表失败: {resp['response']}")
        return []

    def get_robot_token(self) -> Optional[str]:
        resp = request_api(
            "https://user-api.smzdm.com/robot/token",
            method="post",
            headers=self.get_headers(),
        )
        if resp["isSuccess"]:
            return ((resp["data"].get("data") or {}).get("token") or "")
        self.log(f"Robot Token 获取失败！{resp['response']}")
        return None

    def get_tag_detail(self, tag_id: str) -> Dict[str, Any]:
        resp = request_api(
            "https://common-api.smzdm.com/lanmu/config_data",
            method="get",
            headers=self.get_headers(),
            data={"middle_page": "", "tab_selects": "", "redirect_params": tag_id},
        )
        if resp["isSuccess"]:
            return (resp["data"].get("data") or {})
        self.log(f"获取栏目信息失败！{resp['response']}")
        return {}

    def get_tag_by_random(self) -> Optional[Dict[str, Any]]:
        resp = request_api(
            "https://dingyue-api.smzdm.com/tuijian/search_result",
            method="get",
            headers=self.get_headers(),
            data={"time_code": "", "nav_id": "", "type": "tag", "limit": 20},
        )
        if resp["isSuccess"]:
            rows = ((resp["data"].get("data") or {}).get("rows") or [])
            return random.choice(rows) if rows else None
        self.log(f"获取栏目列表失败！{resp['response']}")
        return None

    def get_article_detail(self, article_id: str) -> Optional[Dict[str, Any]]:
        resp = request_api(
            f"https://article-api.smzdm.com/article_detail/{article_id}",
            method="get",
            headers=self.get_headers(),
            data={
                "comment_flow": "",
                "hashcode": "",
                "lastest_update_time": "",
                "uhome": 0,
                "imgmode": 0,
                "article_channel_id": 0,
                "h5hash": "",
            },
        )
        if resp["isSuccess"]:
            return (resp["data"].get("data") or {})
        self.log(f"获取文章详情失败！{resp['response']}")
        return None

    def get_haojia_detail(self, haojia_id: str) -> Optional[Dict[str, Any]]:
        resp = request_api(
            f"https://haojia-api.smzdm.com/detail/{haojia_id}",
            method="get",
            headers=self.get_headers(),
            data={"imgmode": 0, "hashcode": "", "h5hash": ""},
        )
        if resp["isSuccess"]:
            return (resp["data"].get("data") or {})
        self.log(f"获取好价详情失败！{resp['response']}")
        return None

    def favorite(self, *, method: str, aid: str, channel_id: str) -> Dict[str, Any]:
        touchstone = self.get_touchstone_event(
            {
                "event_value": {"aid": aid, "cid": channel_id, "is_detail": True},
                "sourceMode": "我的_我的任务页",
                "sourcePage": f"Android/长图文/P/{aid}/",
                "upperLevel_url": "个人中心/赚奖励/",
            }
        )
        resp = request_api(
            f"https://user-api.smzdm.com/favorites/{method}",
            method="post",
            headers=self.get_headers(),
            data={
                "touchstone_event": touchstone,
                "token": self.token,
                "id": aid,
                "channel_id": channel_id,
            },
        )
        if resp["isSuccess"]:
            self.log(f"{method} 收藏成功: {aid}")
        else:
            self.log(f"{method} 收藏失败！{resp['response']}")
        return {"isSuccess": resp["isSuccess"], "response": resp["response"]}

    def get_touchstone_event(self, obj: Dict[str, Any]) -> str:
        default_obj = {
            "search_tv": "f",
            "sourceRoot": "个人中心",
            "trafic_version": (
                "113_a,115_b,116_e,118_b,131_b,132_b,134_b,136_b,139_a,144_a,150_b,153_a,179_a,"
                "183_b,185_b,188_b,189_b,193_a,196_b,201_a,204_a,205_a,208_b,222_b,226_a,228_a,"
                "22_b,230_b,232_b,239_b,254_a,255_b,256_b,258_b,260_b,265_a,267_a,269_a,270_c,"
                "273_b,276_a,278_a,27_a,280_a,281_a,283_b,286_a,287_a,290_a,291_b,295_a,302_a,"
                "306_b,308_b,312_b,314_a,317_a,318_a,322_b,325_a,326_a,329_b,32_c,332_b,337_c,"
                "341_a,347_a,349_b,34_a,351_a,353_b,355_a,357_b,366_b,373_B,376_b,378_b,380_b,"
                "388_b,391_b,401_d,403_b,405_b,407_b,416_a,421_a,424_b,425_b,427_a,436_b,43_j,"
                "440_a,442_a,444_b,448_a,450_b,451_b,454_b,455_a,458_c,460_a,463_c,464_b,466_b,"
                "467_b,46_a,470_b,471_b,474_b,475_a,484_b,489_a,494_b,496_b,498_a,500_a,503_b,"
                "507_b,510_bb,512_b,515_a,520_a,522_b,525_c,527_b,528_a,59_a,65_b,85_b,102_b,"
                "103_a,106_b,107_b,10_f,11_b,120_a,143_b,157_g,158_c,159_c,160_f,161_d,162_e,"
                "163_a,164_a,165_a,166_f,171_a,174_a,175_e,176_d,209_b,225_a,235_a,236_b,237_c,"
                "272_b,296_c,2_f,309_a,315_b,334_a,335_d,339_b,346_b,361_b,362_d,367_b,368_a,369_e,"
                "374_b,381_c,382_b,383_d,385_b,386_c,389_i,38_b,390_d,396_a,398_b,3_a,413_a,417_a,"
                "418_c,419_b,420_b,422_e,428_a,430_a,431_d,432_e,433_a,437_b,438_c,478_b,479_b,47_a,"
                "480_a,481_b,482_a,483_a,488_b,491_j,492_j,504_b,505_a,514_a,518_b,52_d,53_d,54_v,"
                "55_z1,56_z3,66_a,67_i,68_a1,69_i,74_i,77_d,93_a"
            ),
            "tv": "z1",
        }
        merged = {**default_obj, **obj}
        return json.dumps(merged, ensure_ascii=False)

    def follow_brand(self, *, method: str, keyword_id: str, keyword: str) -> Dict[str, Any]:
        touchstone = self.get_touchstone_event(
            {
                "event_value": {"cid": "44", "is_detail": True, "aid": str(keyword_id)},
                "sourceMode": "百科_品牌详情页",
                "sourcePage": f"Android/其他/品牌详情页/{keyword}/{keyword_id}/",
                "upperLevel_url": "个人中心/赚奖励/",
            }
        )
        resp = request_api(
            "https://dingyue-api.smzdm.com/dy/util/api/user_action",
            method="post",
            headers=self.get_headers(),
            data={
                "action": method,
                "params": json.dumps({"keyword": keyword_id, "keyword_id": keyword_id, "type": "brand"}, ensure_ascii=False),
                "refer": f"Android/其他/品牌详情页/{keyword}/{keyword_id}/",
                "touchstone_event": touchstone,
            },
        )
        if resp["isSuccess"]:
            self.log(f"{method} 关注成功: {keyword}")
        else:
            self.log(f"{method} 关注失败！{resp['response']}")
        return {"isSuccess": resp["isSuccess"], "response": resp["response"]}

    def get_brand_detail(self, brand_id: str) -> Dict[str, Any]:
        resp = request_api(
            "https://brand-api.smzdm.com/brand/brand_basic",
            method="get",
            headers=self.get_headers(),
            data={"brand_id": brand_id},
        )
        if resp["isSuccess"]:
            return (resp["data"].get("data") or {})
        self.log(f"获取品牌信息失败！{resp['response']}")
        return {}

    def get_article_list_from_lanmu(self, lanmu_id: str, num: int = 1) -> List[Dict[str, Any]]:
        lanmu_detail = self.get_tag_detail(lanmu_id)
        if not lanmu_detail or not lanmu_detail.get("lanmu_id"):
            return []
        tab = (lanmu_detail.get("tab") or [])
        tab_params = ""
        if tab and isinstance(tab, list):
            tab_params = str((tab[0] or {}).get("params", ""))

        resp = request_api(
            "https://common-api.smzdm.com/lanmu/list_data",
            method="get",
            headers=self.get_headers(),
            data={
                "price_lt": "",
                "order": "",
                "category_ids": "",
                "price_gt": "",
                "referer_article": "",
                "tag_params": "",
                "mall_ids": "",
                "time_sort": "",
                "page": 1,
                "params": lanmu_id,
                "limit": 20,
                "tab_params": tab_params,
            },
        )
        if resp["isSuccess"]:
            rows = ((resp["data"].get("data") or {}).get("rows") or [])
            return rows[: max(num, 0)]
        self.log(f"获取文章列表失败: {resp['response']}")
        return []

    def rating(self, *, method: str, aid: str, channel_id: str, wtype: Optional[int]) -> Dict[str, Any]:
        touchstone = self.get_touchstone_event(
            {
                "event_value": {"aid": aid, "cid": channel_id, "is_detail": True},
                "sourceMode": "栏目页",
                "sourcePage": f"Android//P/{aid}/",
                "upperLevel_url": "栏目页///",
            }
        )
        data: Dict[str, Any] = {
            "touchstone_event": touchstone,
            "token": self.token,
            "id": aid,
            "channel_id": channel_id,
            "wtype": wtype,
        }
        resp = request_api(
            f"https://user-api.smzdm.com/rating/{method}",
            method="post",
            headers=self.get_headers(),
            data=data,
        )
        if resp["isSuccess"]:
            self.log(f"{method} 点赞成功: {aid}")
        else:
            self.log(f"{method} 点赞失败！{resp['response']}")
        return {"isSuccess": resp["isSuccess"], "response": resp["response"]}

    def submit_comment(self, *, article_id: str, channel_id: str, content: str) -> Dict[str, Any]:
        touchstone = self.get_touchstone_event(
            {
                "event_value": {"aid": article_id, "cid": channel_id, "is_detail": True},
                "sourceMode": "好物社区_全部",
                "sourcePage": f"Android/长图文/{article_id}/评论页/",
                "upperLevel_url": "好物社区/首页/全部/",
                "sourceRoot": "社区",
            }
        )
        resp = request_api(
            "https://comment-api.smzdm.com/comments/submit",
            method="post",
            headers=self.get_headers(),
            data={
                "touchstone_event": touchstone,
                "is_like": 3,
                "reply_from": 3,
                "smiles": 0,
                "atta": 0,
                "parentid": 0,
                "token": self.token,
                "article_id": article_id,
                "channel_id": channel_id,
                "content": content,
            },
        )
        if resp["isSuccess"]:
            cid = (((resp["data"].get("data") or {}).get("comment_ID")) or "")
            self.log(f"评论发表成功: {cid}")
        else:
            self.log(f"评论发表失败！{resp['response']}")
        return {"isSuccess": resp["isSuccess"], "data": resp.get("data"), "response": resp["response"]}

    def remove_comment(self, comment_id: str) -> Dict[str, Any]:
        resp = request_api(
            "https://comment-api.smzdm.com/comments/delete_comment",
            method="post",
            headers=self.get_headers(),
            data={"comment_id": comment_id},
        )
        if resp["isSuccess"]:
            self.log(f"评论删除成功: {comment_id}")
        else:
            self.log(f"评论删除失败！{resp['response']}")
        return {"isSuccess": resp["isSuccess"], "response": resp["response"]}

    def get_dingyue_status(self, name: str) -> Dict[str, Any]:
        resp = request_api(
            "https://dingyue-api.smzdm.com/dingyue/follow_status",
            method="post",
            headers=self.get_headers(),
            data={"rules": json.dumps([{"type": "tag", "keyword": name}], ensure_ascii=False)},
        )
        if resp["isSuccess"]:
            return resp.get("data") or {}
        self.log(f"获取订阅状态失败: {resp['response']}")
        return {}

    def get_article_list_from_tag(self, tag_id: str, name: str, num: int = 1) -> List[Dict[str, Any]]:
        status = self.get_dingyue_status(name)
        smzdm_id = ""
        if isinstance(status, dict):
            smzdm_id = str(status.get("smzdm_id", ""))

        resp = request_api(
            "https://tag-api.smzdm.com/theme/detail_feed",
            method="get",
            headers=self.get_headers(),
            data={
                "article_source": 1,
                "past_num": 0,
                "feed_sort": 2,
                "smzdm_id": smzdm_id,
                "tag_id": tag_id,
                "name": name,
                "time_sort": 0,
                "page": 1,
                "article_tab": 0,
                "limit": 20,
            },
        )
        if resp["isSuccess"]:
            rows = ((resp["data"].get("data") or {}).get("rows") or [])
            return rows[: max(num, 0)]
        self.log(f"获取文章列表失败: {resp['response']}")
        return []

    def get_article_channel_id_for_testing(self, url: str) -> Optional[str]:
        resp = request_api(
            url,
            method="get",
            headers=self.get_headers(),
            parse_json_resp=False,
            sign=False,
        )
        if not resp["isSuccess"]:
            self.log(f"获取文章信息失败！{resp['response']}")
            return None

        html = resp["data"]
        m = re.search(r"'channel_id'\s*:\s*'(\d+)'", html or "")
        if not m:
            self.log(f"获取文章信息失败！{resp['response']}")
            return None
        return m.group(1)

    # ---------------------- 子类需要实现：领取奖励 ----------------------
    def receive_reward(self, task_id: str) -> Dict[str, Any]:
        raise NotImplementedError


__all__ = ["SmzdmTaskBot"]
