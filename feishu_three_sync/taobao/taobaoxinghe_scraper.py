#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘宝星河爬虫 
================
基于浏览器拦截确认过的真实 API，抓取订单详情、推广效果、达人列表。

特点：
- 支持命令行传 orderId / projectId / projectName / settleSeqId / 时间范围。
- 推广效果明细和达人列表会自动翻页，保存完整数据，不只保存第一页样例。
- 输出同时保留 normalized 标准化字段和 raw 原始 API 响应，方便后续补字段。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

warnings.filterwarnings("ignore", message="Pandas requires version .*")

import pandas as pd
import requests

BASE_URL = "https://adstar.alimama.com"
SCRIPT_DIR = Path(__file__).resolve().parent

DEFAULT_ORDER_ID = "117438653"
DEFAULT_PROJECT_ID = "10005556011"


class ApiError(RuntimeError):
    pass


def clean_cookie_text(raw: str) -> str:
    raw = (raw or "").strip().lstrip("\ufeff")
    if "\t" in raw[:10]:
        raw = raw.split("\t")[-1]
    return raw.strip()


def cookie_text_from_json_payload(data: Dict[str, Any]) -> str:
    if not isinstance(data, dict):
        return ""
    for key in ("cookieString", "cookie_string", "rawString", "raw_string", "cookie", "cookiesText"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return clean_cookie_text(value)
    cookies = data.get("cookies")
    if isinstance(cookies, dict):
        return "; ".join(f"{key}={value}" for key, value in cookies.items() if value not in (None, ""))
    scalar_items = {
        key: value
        for key, value in data.items()
        if isinstance(value, (str, int, float, bool)) and value not in (None, "")
    }
    if scalar_items:
        return "; ".join(f"{key}={value}" for key, value in scalar_items.items())
    return ""


def cookie_text_from_payload(raw: str) -> str:
    text = clean_cookie_text(raw)
    if not text:
        return ""
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            pass
        else:
            if not isinstance(data, dict):
                return text
            parsed = cookie_text_from_json_payload(data)
            return parsed or text
    for line in reversed(text.splitlines()):
        line = clean_cookie_text(line)
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        parsed = cookie_text_from_json_payload(data)
        if parsed:
            return parsed
    lines = [clean_cookie_text(line) for line in text.splitlines() if clean_cookie_text(line)]
    if lines:
        return lines[-1]
    return text


def parse_cookie_string(raw: str) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    for item in cookie_text_from_payload(raw).split(";"):
        item = item.strip()
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        if key:
            cookies[key] = value.strip()
    return cookies


def candidate_cookie_paths() -> Iterable[Path]:
    yield SCRIPT_DIR / "adstar.txt"


def load_cookies() -> Tuple[Dict[str, str], Path]:
    for path in candidate_cookie_paths():
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8").strip()
        cookies = parse_cookie_string(raw)
        if cookies:
            return cookies, path
    raise FileNotFoundError("No usable Cookie file found. Place adstar.txt in the script directory.")


def first_value(data: Dict[str, Any], keys: Iterable[str], default: Any = "") -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def list_from_model(model: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if isinstance(model, list):
        return model, {}
    if not isinstance(model, dict):
        return [], {}
    for key in ("result", "list", "data", "records", "items"):
        value = model.get(key)
        if isinstance(value, list):
            return value, model
    return [], model


def to_number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    text = str(value).replace(",", "").replace("¥", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def json_cell(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    else:
        text = str(value)
    return text[:32000]


def excel_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {key: json_cell(value) for key, value in row.items()}


def extract_query_id(value: str, key: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    params = parse_qs(parsed.query)
    return (params.get(key) or [""])[0]


def infer_input(value: str) -> Dict[str, str]:
    value = (value or "").strip()
    if not value:
        return {"mode": "", "project_id": "", "order_id": "", "project_name": ""}
    if value.isdigit():
        if len(value) >= 11:
            return {"mode": "project", "project_id": value, "order_id": "", "project_name": ""}
        return {"mode": "order", "project_id": "", "order_id": value, "project_name": ""}
    project_id = extract_query_id(value, "projectId")
    order_id = extract_query_id(value, "orderId")
    if order_id:
        return {"mode": "order", "project_id": project_id, "order_id": order_id, "project_name": ""}
    if project_id:
        return {"mode": "project", "project_id": project_id, "order_id": "", "project_name": ""}
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) >= 11:
        return {"mode": "project", "project_id": digits, "order_id": "", "project_name": ""}
    if digits and value == digits:
        return {"mode": "order", "project_id": "", "order_id": digits, "project_name": ""}
    return {"mode": "project-name", "project_id": "", "order_id": "", "project_name": value}


def format_money(value: Any) -> str:
    number = to_number(value)
    if number == 0:
        return "0.00"
    return f"{number:.2f}"


def format_bool_cn(value: Any) -> str:
    if value is True:
        return "是"
    if value is False:
        return "否"
    return "" if value in (None, "") else str(value)


def date_range_with_days(start_time: Any, end_time: Any) -> str:
    if not start_time and not end_time:
        return ""
    text = f"{start_time or ''}至{end_time or ''}"
    try:
        start_date = datetime.strptime(str(start_time)[:10], "%Y-%m-%d")
        end_date = datetime.strptime(str(end_time)[:10], "%Y-%m-%d")
        return f"{text}，{(end_date - start_date).days + 1}天"
    except ValueError:
        return text


def compact_json(value: Any) -> str:
    if value in (None, ""):
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def pick_service_provider(model: Dict[str, Any]) -> str:
    providers = model.get("serviceProviderList") or []
    if providers and isinstance(providers[0], dict):
        return providers[0].get("name", "")
    provider = model.get("bearServiceProvider")
    if isinstance(provider, dict):
        return provider.get("name", "")
    return ""


def content_budget(model: Dict[str, Any]) -> Any:
    if model.get("orderSeedBudget") not in (None, ""):
        return model.get("orderSeedBudget")
    for item in model.get("orderScheduleBudgetInfoDetail") or []:
        if isinstance(item, dict) and item.get("resourceModeDesc") == "内容":
            return item.get("budget")
    return ""


def value_if_present(data: Dict[str, Any], key: str) -> Any:
    if key not in data:
        return ""
    return data.get(key)


class TaobaoXingheScraperV5:
    def __init__(
        self,
        *,
        cookies: Dict[str, str],
        debug: bool = True,
        sleep_seconds: float = 0.2,
    ):
        self.debug = debug
        self.sleep_seconds = sleep_seconds
        self._project_products_cache: Dict[str, List[Dict[str, Any]]] = {}
        self.session = requests.Session()
        self.session.cookies.update(cookies)
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": f"{BASE_URL}/portal/v2/pages/myAdstar/project/detail.htm",
                "Origin": BASE_URL,
                "X-Requested-With": "XMLHttpRequest",
            }
        )
        self.tb_token = self._find_tb_token()

    def log(self, message: str):
        if self.debug:
            print(message, flush=True)

    def _find_tb_token(self) -> str:
        for name, value in self.session.cookies.items():
            if "tb_token" in name.lower():
                return value
        return ""

    def get_json(self, path: str, params: Dict[str, Any], *, timeout: int = 30) -> Dict[str, Any]:
        merged = {"bizCode": "adstar", "_tb_token_": self.tb_token, **params}
        url = f"{BASE_URL}{path}"
        response = self.session.get(url, params=merged, timeout=timeout)
        try:
            data = response.json()
        except ValueError:
            data = {"success": False, "httpStatus": response.status_code, "body": response.text[:1000]}

        if response.status_code >= 400:
            raise ApiError(f"HTTP {response.status_code} {path}: {json.dumps(data, ensure_ascii=False)[:1200]}")
        if isinstance(data, dict) and not data.get("success", True):
            raise ApiError(f"API Error {path}: {json.dumps(data, ensure_ascii=False)[:1200]}")
        return data

    def get_order_detail(self, order_id: str) -> Dict[str, Any]:
        self.log(f"\n[Tab1] 订单详情 orderId={order_id}")
        data = self.get_json("/api/one/order/get", {"orderId": order_id}, timeout=30)
        model = data.get("model") or {}
        if not isinstance(model, dict) or not model:
            raise ApiError(f"订单详情为空: {json.dumps(data, ensure_ascii=False)[:1000]}")

        service_fee = to_number((model.get("serviceFee") or {}).get("serviceFeeBudget"))
        budget = to_number(first_value(model, ("budget", "orderBudget"), 0))
        normalized = {
            "项目名称": model.get("projectName", ""),
            "订单id": first_value(model, ("buyOrderId", "orderId"), order_id),
            "订单名称": model.get("orderName", ""),
            "推广媒体": model.get("mediaDesc", ""),
            "合作模式": first_value(model, ("deliveryModeDesc", "businessModeDesc")),
            "资源类型": model.get("resourceModeDesc", ""),
            "服务商名称": pick_service_provider(model),
            "投放时间": date_range_with_days(model.get("startTime"), model.get("endTime")),
            "联系方式": model.get("contactInfo", ""),
            "达人意向": first_value(model, ("intentionKoxInfos", "creatorIntent", "spSelectMode"), "--"),
            "总预算": budget,
            "订单总金额": round(budget + service_fee, 2),
            "平台服务费": service_fee,
            "内容预算": content_budget(model),
            "投放要求": "--",
            "推广店铺": model.get("adTargetShopName", ""),
            "订单状态": model.get("orderStatusDesc", ""),
            "项目ID": model.get("projectId", ""),
            "结算单号": model.get("settleSeqId", ""),
            "商品ID列表": ",".join(str(item) for item in model.get("itemIds") or []),
            "下单时间": model.get("gmtCreate", ""),
            "更新时间": model.get("gmtModified", ""),
        }
        self.log(f"   OK {normalized['项目名称']} | {normalized['推广媒体']} | {normalized['订单状态']}")
        return {"normalized": normalized, "raw": data}

    def get_event_info_detail(self, settle_seq_id: str) -> Dict[str, Any]:
        self.log(f"\n[Tab1-B] 订单任务详情 eventId={settle_seq_id}")
        data = self.get_json("/api/cpa/event/info/detail", {"eventId": settle_seq_id}, timeout=30)
        model = data.get("model") or {}
        if not isinstance(model, dict):
            model = {}
        self.log("   OK 任务详情")
        return {"normalized": model, "raw": data}

    def get_order_products(self, order_id: str, product_unique_key: str = "", page_size: int = 100) -> List[Dict[str, Any]]:
        self.log(f"\n[Tab1-C] 推广商品 orderId={order_id}")
        products: List[Dict[str, Any]] = []
        page_no = 1
        while True:
            data = self.get_json(
                "/api/one/pallet/order/item/list",
                {"orderId": order_id, "pageNo": page_no, "pageSize": page_size},
                timeout=30,
            )
            items, _model = list_from_model(data.get("model"))
            for item in items:
                if not isinstance(item, dict):
                    continue
                products.append(
                    {
                        "商品ID": item.get("itemId", ""),
                        "商品标题": item.get("itemTitle", ""),
                        "商品图片": item.get("itemPic", ""),
                        "商品价格": item.get("itemPrice", ""),
                        "销量": item.get("saleCnt", ""),
                        "商品标签": compact_json(item.get("itemLabelList")),
                    }
                )
            if len(items) < page_size:
                break
            page_no += 1
            time.sleep(self.sleep_seconds)

        if product_unique_key:
            try:
                detail = self.get_json("/api/oneproduct/detail", {"productUniqueKey": product_unique_key}, timeout=30)
                model = detail.get("model") or {}
                for product in products:
                    product["产品ID"] = model.get("productId", "")
                    product["产品唯一Key"] = model.get("productUniqueKey", "")
            except ApiError:
                pass

        self.log(f"   OK 商品 {len(products)} 条")
        return products

    def build_effect_ext(self, *, settle_seq_id: str, project_id: str) -> str:
        return json.dumps(
            {
                "settleSeqId": int(settle_seq_id),
                "media": "RED_BOOK",
                "saleType": 1,
                "businessMode": 88,
                "deliveryMode": "cptSeedDaily",
                "projectId": int(project_id),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def get_effect_summary(
        self,
        *,
        settle_seq_id: str,
        project_id: str,
        start_time: str,
        end_time: str,
    ) -> Dict[str, Any]:
        self.log("\n[Tab2-A] 推广效果汇总")
        data = self.get_json(
            "/api/report/multiscene/query/summary/data",
            {
                "bizType": "selfOfficial_orderSum_summary",
                "startTime": start_time,
                "endTime": end_time,
                "ext": self.build_effect_ext(settle_seq_id=settle_seq_id, project_id=project_id),
            },
            timeout=30,
        )
        model = data.get("model") or {}
        if not isinstance(model, dict):
            model = {}

        field_map = [
            ("阅读播放UV", "readUv1d"),
            ("点赞UV", "likeUv1d"),
            ("评论UV", "commentUv1d"),
            ("收藏UV", "favoriteUv1d"),
            ("转发UV", "forwardUv1d"),
            ("互动UV", "engagementUv1d"),
            ("内容互动率%", "contentEngagementRate"),
            ("搜索曝光UV", "slrAttrItmSeImpsUv1d"),
            ("搜索进店UV", "slrAttrSlrSeVstUv1d"),
            ("进店UV", "slrAttrSlrVstUv1d"),
            ("新客进店UV", "slrAttrSlrVstUv1dNew"),
            ("商品收藏UV", "slrAttrItmCltUv1d"),
            ("商品加购UV", "slrAttrItmCltCartUv1d"),
            ("关注店铺UV", "slrAttrSlrSubUv1d"),
            ("店铺会员UV", "slrAttrSlrMbrUv1d"),
            ("成交UV", "slrAttrItmOrdUv1d"),
            ("新客成交UV", "slrAttrItmOrdUv1dNew"),
            ("商家GMV", "slrAttrItmOrdGmv1d"),
            ("订单商品成交GMV", "slrAttrItmOrdGmv1d1bpOrd"),
            ("非订单商品成交GMV", "slrAttrItmOrdGmv1dNot1bpOrd"),
            ("订单商品新客成交GMV", "slrAttrItmOrdGmv1d1bpOrdNew"),
            ("预售付定GMV", "slrAttrItmOrdSubpayGmv1d"),
            ("预售整单预估GMV", "slrAttrItmOrdSubpayGmv1dPredAll"),
            ("预售付定UV", "slrAttrItmOrdSubpayUv1d"),
            ("成交转化率%", "conversionRate"),
        ]
        normalized = {label: model[key] for label, key in field_map if key in model and model[key] is not None}
        self.log(f"   OK 汇总指标 {len(normalized)} 个")
        return {"normalized": normalized, "raw": data}

    def get_effect_details(
        self,
        *,
        settle_seq_id: str,
        project_id: str,
        start_time: str,
        end_time: str,
        page_size: int,
    ) -> Dict[str, Any]:
        self.log("\n[Tab2-B] 推广效果明细")
        records: List[Dict[str, Any]] = []
        raw_pages: List[Dict[str, Any]] = []
        page_no = 1
        while True:
            data = self.get_json(
                "/api/report/multiscene/query/detail/data",
                {
                    "bizType": "selfOfficial_orderInfo_detail",
                    "dataBatch": "order",
                    "pageNo": page_no,
                    "pageSize": page_size,
                    "startTime": start_time,
                    "endTime": end_time,
                    "ext": self.build_effect_ext(settle_seq_id=settle_seq_id, project_id=project_id),
                },
                timeout=30,
            )
            raw_pages.append(data)
            page_records, _model = list_from_model(data.get("model"))
            records.extend(page_records)
            self.log(f"   page {page_no}: {len(page_records)} 条")
            if len(page_records) < page_size:
                break
            page_no += 1
            time.sleep(self.sleep_seconds)

        normalized = [
            {
                "日期": first_value(item, ("ds", "theDate")),
                "阅读播放UV": value_if_present(item, "readUv1d"),
                "点赞UV": value_if_present(item, "likeUv1d"),
                "评论UV": value_if_present(item, "commentUv1d"),
                "收藏UV": value_if_present(item, "favoriteUv1d"),
                "转发UV": value_if_present(item, "forwardUv1d"),
                "互动UV": value_if_present(item, "engagementUv1d"),
                "内容互动率%": value_if_present(item, "contentEngagementRate"),
                "搜索曝光UV": value_if_present(item, "slrAttrItmSeImpsUv1d"),
                "搜索进店UV": value_if_present(item, "slrAttrSlrSeVstUv1d"),
                "进店UV": value_if_present(item, "slrAttrSlrVstUv1d"),
                "新客进店UV": value_if_present(item, "slrAttrSlrVstUv1dNew"),
                "商品收藏UV": value_if_present(item, "slrAttrItmCltUv1d"),
                "商品加购UV": value_if_present(item, "slrAttrItmCltCartUv1d"),
                "关注店铺UV": value_if_present(item, "slrAttrSlrSubUv1d"),
                "店铺会员UV": value_if_present(item, "slrAttrSlrMbrUv1d"),
                "成交UV": value_if_present(item, "slrAttrItmOrdUv1d"),
                "新客成交UV": value_if_present(item, "slrAttrItmOrdUv1dNew"),
                "商家GMV": value_if_present(item, "slrAttrItmOrdGmv1d"),
                "订单商品成交GMV": value_if_present(item, "slrAttrItmOrdGmv1d1bpOrd"),
                "非订单商品成交GMV": value_if_present(item, "slrAttrItmOrdGmv1dNot1bpOrd"),
                "订单商品新客成交GMV": value_if_present(item, "slrAttrItmOrdGmv1d1bpOrdNew"),
                "预售付定GMV": value_if_present(item, "slrAttrItmOrdSubpayGmv1d"),
                "预售整单预估GMV": value_if_present(item, "slrAttrItmOrdSubpayGmv1dPredAll"),
                "预售付定UV": value_if_present(item, "slrAttrItmOrdSubpayUv1d"),
                "成交转化率%": value_if_present(item, "conversionRate"),
            }
            for item in records
        ]
        self.log(f"   OK 明细合计 {len(records)} 条")
        return {"normalized": normalized, "raw_pages": raw_pages}

    def get_creator_list(
        self,
        *,
        settle_seq_id: str,
        page_size: int,
    ) -> Dict[str, Any]:
        self.log("\n[Tab3] 达人列表")
        creators: List[Dict[str, Any]] = []
        raw_pages: List[Dict[str, Any]] = []
        page_no = 1
        seen_fingerprints = set()
        MAX_PAGES = 100
        while page_no <= MAX_PAGES:
            data = self.get_json(
                "/api/cpa/media/seed/event/sponsor/list",
                {
                    "eventId": settle_seq_id,
                    "pageNo": page_no,
                    "pageSize": page_size,
                    "mediaType": "RED_BOOK",
                    "sceneCode": 1,
                    "platformVersion": 1,
                },
                timeout=30,
            )
            raw_pages.append(data)
            page_records, _model = list_from_model(data.get("model"))

            # 重复页判定
            import hashlib
            fp = hashlib.sha256(json.dumps(page_records, sort_keys=True).encode("utf-8")).hexdigest()
            if fp in seen_fingerprints and page_records:
                self.log(f"   [Warning] page {page_no}: duplicate page detected, terminating pagination")
                break
            seen_fingerprints.add(fp)

            creators.extend(page_records)
            self.log(f"   page {page_no}: {len(page_records)} 人")
            if len(page_records) < page_size:
                break
            page_no += 1
            time.sleep(self.sleep_seconds)

        enriched_creators: List[Dict[str, Any]] = []
        for item in creators:
            if not isinstance(item, dict):
                continue
            detail = self.get_creator_task_detail(
                event_id=settle_seq_id,
                advertising_campaign_id=item.get("advertisingCampaignId"),
            )
            enriched_creators.append({**item, **detail})
            time.sleep(self.sleep_seconds)

        normalized: List[Dict[str, Any]] = []
        total_amount = 0.0
        total_creator_fee = 0.0
        total_service_fee = 0.0
        for index, item in enumerate(enriched_creators, 1):
            order_amount = to_number(first_value(item, ("mediaTotalFee", "amount", "settleAmount"), 0))
            creator_fee = to_number(item.get("koxCommissionFee")) if item.get("koxCommissionFee") not in (None, "") else 0.0
            service_fee = to_number(item.get("mediaPlatformFee")) if item.get("mediaPlatformFee") not in (None, "") else 0.0
            total_amount += order_amount
            total_creator_fee += creator_fee
            total_service_fee += service_fee
            normalized.append(
                {
                    "序号": index,
                    "任务ID": first_value(item, ("mediaEventId", "eventId", "id")),
                    "蒲公英任务名称": first_value(item, ("mediaEventName", "eventName")),
                    "蒲公英ID": first_value(item, ("mediaEventId", "eventId")),
                    "达人昵称": first_value(item, ("koxNickName", "nickName", "creatorNick")),
                    "媒体": first_value(item, ("mediaTypeDesc", "mediaName", "media")),
                    "内容URL": first_value(item, ("contentUrl", "url")),
                    "达人费用": round(creator_fee, 2) if item.get("koxCommissionFee") not in (None, "") else "",
                    "小红书服务费": round(service_fee, 2) if item.get("mediaPlatformFee") not in (None, "") else "",
                    "达人下单金额": round(order_amount, 2) if order_amount else "",
                    "内容预计发布时间": item.get("contentExpectPublishTime", ""),
                    "内容实际回传时间": item.get("startTime", ""),
                    "媒体任务状态": first_value(item, ("statusMsg", "itemStatusName", "scheduleStatusName")),
                    "是否授权内容上传": format_bool_cn(item.get("isContentAuthorized")),
                    "内容链接": first_value(item, ("contentUrl", "url")),
                    "过期时间": item.get("expireTime", ""),
                    "广告活动ID": item.get("advertisingCampaignId", ""),
                    "raw": item,
                }
            )
        self.log(f"   OK 达人合计 {len(normalized)} 人，总金额 {total_amount:,.2f}")
        return {
            "summary": {
                "任务总金额": round(total_amount, 2),
                "达人数量": len(normalized),
                "达人占用金额": round(total_amount, 2),
                "达人费用总额": round(total_creator_fee, 2) if total_creator_fee else "",
                "小红书服务费总额": round(total_service_fee, 2) if total_service_fee else "",
                "达人下单总金额": round(total_amount, 2),
            },
            "normalized": normalized,
            "raw_pages": raw_pages,
        }

    def get_creator_task_detail(self, event_id: str, advertising_campaign_id: Any) -> Dict[str, Any]:
        if not event_id or advertising_campaign_id in (None, ""):
            return {}
        data = self.get_json(
            "/openapi/param2/1/gateway.unionpub/union.adstar.media.seed.event.get.json",
            {"eventId": event_id, "advertisingCampaignId": advertising_campaign_id},
            timeout=30,
        )
        rows = data.get("data")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return rows[0]
        return {}

    def get_order_list(self, project_id: str, page_size: int) -> List[Dict[str, Any]]:
        self.log(f"\n[Project] 订单列表 projectId={project_id}")
        orders: List[Dict[str, Any]] = []
        page_no = 1
        while True:
            data = self.get_json(
                "/api/one/order/list",
                {"projectId": project_id, "pageNo": page_no, "pageSize": page_size},
                timeout=30,
            )
            page_orders, _model = list_from_model(data.get("model"))
            orders.extend(page_orders)
            self.log(f"   page {page_no}: {len(page_orders)} 个订单")
            if len(page_orders) < page_size:
                break
            page_no += 1
            time.sleep(self.sleep_seconds)
        return orders

    def get_project_list(self, *, project_name: str, page_size: int) -> List[Dict[str, Any]]:
        self.log(f"\n[ProjectSearch] 项目列表 projectName={project_name}")
        projects: List[Dict[str, Any]] = []
        page_no = 1
        while True:
            params: Dict[str, Any] = {"pageNo": page_no, "pageSize": page_size}
            if project_name:
                params["projectName"] = project_name
            data = self.get_json("/api/one/deliveryProject/list", params, timeout=30)
            page_projects, model = list_from_model(data.get("model"))
            projects.extend(page_projects)
            total_count = model.get("totalCount", "") if isinstance(model, dict) else ""
            self.log(f"   page {page_no}: {len(page_projects)} 个项目，总数 {total_count or '-'}")
            has_next = bool(model.get("hasNext")) if isinstance(model, dict) else len(page_projects) >= page_size
            if not has_next or len(page_projects) < page_size:
                break
            page_no += 1
            time.sleep(self.sleep_seconds)
        return projects

    def scrape_order(
        self,
        *,
        order_id: str,
        project_id: Optional[str],
        settle_seq_id: Optional[str],
        start_time: Optional[str],
        end_time: Optional[str],
        page_size: int,
    ) -> Dict[str, Any]:
        order = self.get_order_detail(order_id)
        order_norm = order["normalized"]
        resolved_settle_seq_id = str(settle_seq_id or order_norm.get("结算单号") or "")
        resolved_project_id = str(project_id or order_norm.get("项目ID") or DEFAULT_PROJECT_ID)
        if not resolved_settle_seq_id:
            raise ApiError("订单详情中没有 settleSeqId，请用 --settle-seq-id 手动传入")

        event_info = self.get_event_info_detail(resolved_settle_seq_id)
        event_model = event_info.get("normalized") or {}
        event_rule = event_model.get("eventRule") or {}
        event_basic = event_model.get("basicInfo") or {}
        event_item = event_model.get("eventItem") or {}
        if event_rule:
            order_norm["总预算"] = first_value(event_rule, ("totalAmount",), order_norm.get("总预算"))
            order_norm["订单总金额"] = first_value(event_rule, ("totalFee",), order_norm.get("订单总金额"))
            order_norm["平台服务费"] = first_value(event_rule, ("baseServiceFee",), order_norm.get("平台服务费"))
            order_norm["任务规则类型"] = first_value(event_rule, ("ruleTypeName", "subRuleTypeName"))
            order_norm["合作方式"] = first_value(event_rule, ("coopModeDesc",), "")
            order_norm["达人类型"] = compact_json(event_rule.get("talentTypeList"))
        if event_basic:
            order_norm["任务状态"] = event_basic.get("statusDesc", "")
            order_norm["是否授权内容上传"] = format_bool_cn(event_basic.get("isContentAuthorized"))
            order_norm["最后确认时间"] = event_basic.get("lastConfirmTime", "")
            order_norm["最后合作时间"] = event_basic.get("lastCoopTime", "")
        if event_item:
            order_norm["推广店铺"] = event_item.get("shopNickName") or order_norm.get("推广店铺", "")
            order_norm["品牌名称"] = event_item.get("brandName", "")

        if not start_time:
            start_time = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d 00:00:00")
        if not end_time:
            end_time = datetime.now().strftime("%Y-%m-%d 23:59:59")

        effect_summary = self.get_effect_summary(
            settle_seq_id=resolved_settle_seq_id,
            project_id=resolved_project_id,
            start_time=start_time,
            end_time=end_time,
        )
        effect_details = self.get_effect_details(
            settle_seq_id=resolved_settle_seq_id,
            project_id=resolved_project_id,
            start_time=start_time,
            end_time=end_time,
            page_size=page_size,
        )
        creators = self.get_creator_list(settle_seq_id=resolved_settle_seq_id, page_size=page_size)
        order_model = (order.get("raw") or {}).get("model") or {}
        products = self.get_order_products(
            order_id=order_id,
            product_unique_key=order_model.get("productUniqueKey", ""),
            page_size=page_size,
        )

        return {
            "version": "5.2",
            "scrapeTime": datetime.now().isoformat(timespec="seconds"),
            "input": {
                "orderId": order_id,
                "projectId": project_id,
                "settleSeqId": settle_seq_id,
                "startTime": start_time,
                "endTime": end_time,
                "pageSize": page_size,
            },
            "resolved": {
                "orderId": order_id,
                "projectId": resolved_project_id,
                "settleSeqId": resolved_settle_seq_id,
            },
            "orderDetail": order,
            "eventInfo": event_info,
            "effectSummary": effect_summary,
            "effectDetails": effect_details,
            "creatorList": creators,
            "promotionProducts": {"normalized": products},
            "status": {
                "orderDetail": bool(order.get("normalized")),
                "effectSummaryCount": len(effect_summary.get("normalized") or {}),
                "effectDetailCount": len(effect_details.get("normalized") or []),
                "creatorCount": len(creators.get("normalized") or []),
                "productCount": len(products),
            },
        }

    def scrape_project(
        self,
        *,
        project_id: str,
        start_time: Optional[str],
        end_time: Optional[str],
        page_size: int,
    ) -> Dict[str, Any]:
        order_records = self.get_order_list(project_id, page_size=page_size)
        orders: List[Dict[str, Any]] = []
        for index, record in enumerate(order_records, 1):
            order_id = str(first_value(record, ("orderId", "buyOrderId", "id")))
            if not order_id:
                self.log(f"   skip order #{index}: missing orderId")
                continue
            order_name = first_value(record, ("orderName", "name"), "")
            self.log(f"\n[Project] 处理订单 {index}/{len(order_records)} {order_id} {order_name}")
            orders.append(
                self.scrape_order(
                    order_id=order_id,
                    project_id=project_id,
                    settle_seq_id=None,
                    start_time=start_time,
                    end_time=end_time,
                    page_size=page_size,
                )
            )
            time.sleep(self.sleep_seconds)

        return {
            "version": "5.2",
            "scrapeTime": datetime.now().isoformat(timespec="seconds"),
            "input": {"projectId": project_id, "startTime": start_time, "endTime": end_time, "pageSize": page_size},
            "projectId": project_id,
            "orderRecords": order_records,
            "orders": orders,
            "status": {
                "orderCount": len(orders),
                "effectSummaryCount": sum(item["status"]["effectSummaryCount"] for item in orders),
                "effectDetailCount": sum(item["status"]["effectDetailCount"] for item in orders),
                "creatorCount": sum(item["status"]["creatorCount"] for item in orders),
            },
        }

    def scrape_project_search(
        self,
        *,
        project_name: str,
        start_time: Optional[str],
        end_time: Optional[str],
        page_size: int,
    ) -> Dict[str, Any]:
        project_records = self.get_project_list(project_name=project_name, page_size=page_size)
        project_results: List[Dict[str, Any]] = []
        orders: List[Dict[str, Any]] = []
        for index, project in enumerate(project_records, 1):
            project_id = str(first_value(project, ("id", "projectId")))
            if not project_id:
                self.log(f"   skip project #{index}: missing projectId")
                continue
            name = first_value(project, ("projectName", "name"), "")
            self.log(f"\n[ProjectSearch] 处理项目 {index}/{len(project_records)} {project_id} {name}")
            project_result = self.scrape_project(
                project_id=project_id,
                start_time=start_time,
                end_time=end_time,
                page_size=page_size,
            )
            project_result["projectRecord"] = project
            for order in project_result.get("orders") or []:
                order["projectRecord"] = project
            project_results.append(project_result)
            orders.extend(project_result.get("orders") or [])
            time.sleep(self.sleep_seconds)

        return {
            "version": "5.2",
            "scrapeTime": datetime.now().isoformat(timespec="seconds"),
            "input": {"projectName": project_name, "startTime": start_time, "endTime": end_time, "pageSize": page_size},
            "projectName": project_name,
            "projectRecords": project_records,
            "projects": project_results,
            "orders": orders,
            "status": {
                "projectCount": len(project_records),
                "projectWithOrdersCount": len(project_results),
                "orderCount": len(orders),
                "effectSummaryCount": sum(item["status"]["effectSummaryCount"] for item in orders),
                "effectDetailCount": sum(item["status"]["effectDetailCount"] for item in orders),
                "creatorCount": sum(item["status"]["creatorCount"] for item in orders),
            },
        }


def export_three_tab_excel(result: Dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    is_project = "orders" in result
    orders = result["orders"] if is_project else [result]

    order_rows: List[Dict[str, Any]] = []
    effect_rows: List[Dict[str, Any]] = []
    creator_rows: List[Dict[str, Any]] = []

    for item in orders:
        resolved = item.get("resolved") or {}
        order_detail = item.get("orderDetail") or {}
        order_norm = order_detail.get("normalized") or {}
        meta = {
            "订单ID": resolved.get("orderId") or order_norm.get("订单ID") or "",
            "项目ID": resolved.get("projectId") or order_norm.get("项目ID") or "",
            "结算单号": resolved.get("settleSeqId") or order_norm.get("结算单号") or "",
            "订单名称": order_norm.get("订单名称", ""),
        }

        products = ((item.get("promotionProducts") or {}).get("normalized") or [])
        order_raw_columns = {
            key: order_norm.get(key)
            for key in ("订单预算明细", "服务商原始信息", "订单原始数据", "任务详情原始数据")
            if key in order_norm
        }
        order_visible_columns = {
            key: value for key, value in order_norm.items()
            if key not in order_raw_columns
        }
        if order_norm:
            if products:
                for product in products:
                    order_rows.append(excel_row({**meta, **order_visible_columns, **product, **order_raw_columns}))
            else:
                order_rows.append(excel_row({**meta, **order_visible_columns, "推广商品状态": "未获取推广商品", **order_raw_columns}))
        else:
            order_rows.append(excel_row({**meta, "状态": "未获取订单详情"}))

        effect_summary = ((item.get("effectSummary") or {}).get("normalized") or {})
        if effect_summary:
            effect_rows.append(excel_row({**meta, "数据区块": "汇总", **effect_summary}))
        else:
            effect_rows.append(excel_row({**meta, "数据区块": "汇总", "状态": "未获取推广效果汇总"}))

        effect_details = ((item.get("effectDetails") or {}).get("normalized") or [])
        if effect_details:
            for row in effect_details:
                effect_rows.append(excel_row({**meta, "数据区块": "明细", **row}))
        else:
            effect_rows.append(excel_row({**meta, "数据区块": "明细", "状态": "接口未返回推广效果明细"}))

        creators = item.get("creatorList") or {}
        creator_summary = creators.get("summary") or {}
        if creator_summary:
            creator_rows.append(excel_row({**meta, "数据区块": "汇总", **creator_summary}))
        else:
            creator_rows.append(excel_row({**meta, "数据区块": "汇总", "状态": "未获取达人汇总"}))

        creator_details = creators.get("normalized") or []
        if creator_details:
            for row in creator_details:
                clean = {key: value for key, value in row.items() if key != "raw"}
                creator_rows.append(excel_row({**meta, "数据区块": "明细", **clean}))
        else:
            creator_rows.append(excel_row({**meta, "数据区块": "明细", "状态": "接口未返回达人明细"}))

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        pd.DataFrame(order_rows).to_excel(writer, sheet_name="订单详情", index=False)
        pd.DataFrame(effect_rows).to_excel(writer, sheet_name="推广效果", index=False)
        pd.DataFrame(creator_rows).to_excel(writer, sheet_name="达人列表", index=False)
    return output_path


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="淘宝星河订单/项目数据抓取")
    parser.add_argument("id_or_url", nargs="?", default="", help="订单ID、项目ID、项目名称、订单URL或项目URL")
    parser.add_argument("--mode", choices=("auto", "order", "project", "project-name"), default="auto")
    parser.add_argument("--order-id", default=os.environ.get("TAOBAO_XINGHE_ORDER_ID", ""))
    parser.add_argument("--project-id", default=os.environ.get("TAOBAO_XINGHE_PROJECT_ID", ""))
    parser.add_argument("--project-name", default=os.environ.get("TAOBAO_XINGHE_PROJECT_NAME", ""))
    parser.add_argument("--settle-seq-id", default=os.environ.get("TAOBAO_XINGHE_SETTLE_SEQ_ID"))
    parser.add_argument("--start-time", default=os.environ.get("TAOBAO_XINGHE_START_TIME", "2026-05-27 00:00:00"))
    parser.add_argument("--end-time", default=os.environ.get("TAOBAO_XINGHE_END_TIME", "2026-06-11 23:59:59"))
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--output", default="")
    parser.add_argument("--json-output", default="")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def default_output_path(prefix: str, ident: str) -> Path:
    output_dir = SCRIPT_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_dir / f"taobaoxinghe_{prefix}_{ident}_{stamp}.xlsx"


def default_json_output_path(output_path: Path, explicit_path: str = "") -> Path:
    if explicit_path:
        return Path(explicit_path)
    return output_path.with_suffix(".json")


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    inferred = infer_input(args.id_or_url)
    mode = args.mode if args.mode != "auto" else inferred["mode"]
    order_id = args.order_id or inferred["order_id"]
    project_id = args.project_id or inferred["project_id"]
    project_name = args.project_name or inferred["project_name"]
    if not mode:
        mode = "order" if order_id else "project" if project_id else "project-name" if project_name else "order"
    if not order_id and mode == "order":
        order_id = DEFAULT_ORDER_ID
    if not project_id and mode != "project-name":
        project_id = DEFAULT_PROJECT_ID

    cookies, cookie_path = load_cookies()
    if not args.quiet:
        print("=" * 72)
        print("  淘宝星河爬虫 v5.2")
        print("=" * 72)
        print(f"Cookie: {cookie_path} ({len(cookies)} fields)")
        print(f"Mode: {mode} | Order: {order_id or '-'} | Project: {project_id or '-'} | ProjectName: {project_name or '-'}")

    scraper = TaobaoXingheScraperV5(cookies=cookies, debug=not args.quiet)
    if not scraper.tb_token:
        raise ApiError("Cookie 中未找到 _tb_token_，请重新复制登录后的 Cookie")

    page_size = max(1, min(args.page_size, 200))
    if mode == "project":
        result = scraper.scrape_project(
            project_id=str(project_id),
            start_time=args.start_time,
            end_time=args.end_time,
            page_size=page_size,
        )
        output_path = Path(args.output) if args.output else default_output_path("project", str(project_id))
    elif mode == "project-name":
        if not project_name:
            raise ApiError("项目名称为空，请传入项目名称或使用 --project-name")
        result = scraper.scrape_project_search(
            project_name=str(project_name),
            start_time=args.start_time,
            end_time=args.end_time,
            page_size=page_size,
        )
        safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(project_name))[:60] or "project_name"
        output_path = Path(args.output) if args.output else default_output_path("project_name", safe_name)
    elif mode == "order":
        result = scraper.scrape_order(
            order_id=str(order_id),
            project_id=str(project_id) if project_id else None,
            settle_seq_id=str(args.settle_seq_id) if args.settle_seq_id else None,
            start_time=args.start_time,
            end_time=args.end_time,
            page_size=page_size,
        )
        output_path = Path(args.output) if args.output else default_output_path("order", str(order_id))
    else:
        raise ApiError("无法判断输入类型，请传入订单ID、项目ID或使用 --mode 指定")

    export_three_tab_excel(result, output_path)
    json_path = default_json_output_path(output_path, args.json_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    status = result["status"]
    print("\n" + "=" * 72)
    print("抓取完成")
    if mode == "project-name":
        print(f"项目数量: {status['projectCount']} 个")
        print(f"订单数量: {status['orderCount']} 个")
    elif mode == "project":
        print(f"订单数量: {status['orderCount']} 个")
    else:
        print(f"订单详情: {'OK' if status['orderDetail'] else 'FAIL'}")
    print(f"推广汇总: {status['effectSummaryCount']} 个指标")
    print(f"推广明细: {status['effectDetailCount']} 条")
    print(f"达人列表: {status['creatorCount']} 人")
    print(f"输出文件: {output_path}")
    print(f"JSON文件: {json_path}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
