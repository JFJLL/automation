from typing import List, Dict, Any, Tuple
import requests
import json
from app.config import (
    ADSTAR_OSS_BASE_URL, ADSTAR_OSS_OBJECT_KEY,
    JZT_OSS_OBJECT_KEY, JUGUANG_OSS_OBJECT_KEY
)

PLATFORMS = {
    "jzt": {
        "name": "京准通",
        "key_columns": ["任务ID", "任务Id", "taskId"],
        "date_columns": ["日期", "date", "theDate"],
        "vocab": [
            "日期", "任务ID", "任务标题", "平台", "归因范围", "阅读UV", "点赞UV", "收藏UV",
            "评论UV", "分享UV", "搜索浏览UV", "商详浏览UV", "商品加购UV", "商品收藏UV",
            "下单UV", "主推商品下单UV", "下单GMV", "主推商品下单GMV", "成交UV",
            "主推商品成交uv", "成交GMV", "主推商品成交GMV", "新访客UV", "新客UV", "搜索曝光UV"
        ]
    },
    "taobao": {
        "name": "淘宝星河",
        "key_columns": ["任务ID", "内容ID", "订单ID", "orderId", "contentId"],
        "date_columns": ["日期", "时间", "ds", "theDate"],
        "vocab": [
            "日期", "内容ID", "任务ID", "流量类型", "归因口径", "阅读/播放UV", "点赞UV", "评论UV",
            "收藏UV", "转发UV", "互动UV", "内容互动率", "搜索曝光UV", "搜索进店UV", "进店UV",
            "新客进店uv", "商品收藏UV", "商品加购UV", "关注店铺UV", "店铺会员UV", "成交UV",
            "商家GMV", "订单商品成交GMV", "非订单商品成交GMV", "新客成交UV", "订单商品新客成交GMV",
            "预售付定GMV", "预售整单预估GMV", "预售付定UV", "成交转化率", "达人昵称", "内容链接", "订单名称"
        ]
    },
    "juguang": {
        "name": "聚光",
        "key_columns": ["创意ID", "笔记ID", "creativityId", "noteId"],
        "date_columns": ["时间", "日期", "time", "date"],
        "vocab": [
            "时间", "创意名称", "创意ID", "笔记ID", "笔记跳转链接", "单元名称", "单元ID",
            "计划名称", "计划ID", "消费", "展现量", "点击量", "点击率", "平均点击成本",
            "平均千次展示费用", "点赞", "评论", "收藏", "关注", "分享", "互动量", "平均互动成本",
            "行动按钮点击量", "行动按钮点击率", "截图", "保存图片", "小红星站外活跃UV(30日归因)",
            "小红星站外活跃成本(30日归因)", "小红星任务期消费", "搜索组件点击量", "搜索组件点击转化率",
            "平均搜索后阅读笔记篇数", "搜后阅读量", "新增种草人群", "新增种草人群成本", "新增深度种草人群",
            "新增深度种草人群成本", "投放位置", "精准定向", "关键词"
        ]
    }
}

def calculate_match_scores(headers: List[str]) -> Dict[str, Dict[str, Any]]:
    clean_headers = set(str(h).strip() for h in headers if h is not None and str(h).strip())
    scores = {}
    for code, info in PLATFORMS.items():
        vocab_set = set(info["vocab"])
        matched = clean_headers.intersection(vocab_set)
        score = len(matched) / max(len(vocab_set), 1)
        # 匹配到核心ID列权重提升
        id_matched = any(k in clean_headers for k in info["key_columns"])
        scores[code] = {
            "platform_code": code,
            "platform_name": info["name"],
            "matched_count": len(matched),
            "matched_columns": sorted(list(matched)),
            "score": round(score * 100, 1),
            "has_id_column": id_matched
        }
    return scores

def detect_best_platform(headers: List[str]) -> Tuple[str, Dict[str, Any]]:
    scores = calculate_match_scores(headers)
    best_code = max(scores.keys(), key=lambda c: (scores[c]["has_id_column"], scores[c]["score"]))
    return best_code, scores[best_code]

def find_id_column(platform_code: str, headers: List[str]) -> str:
    info = PLATFORMS.get(platform_code)
    if not info:
        return headers[1] if len(headers) > 1 else headers[0]
    for candidate in info["key_columns"]:
        for h in headers:
            if str(h).strip().lower() == candidate.lower():
                return h
    # fallback
    for h in headers:
        if "id" in str(h).lower() or "id" in str(h) or "编号" in str(h):
            return h
    return headers[1] if len(headers) > 1 else headers[0]

def find_date_column(platform_code: str, headers: List[str]) -> str:
    info = PLATFORMS.get(platform_code)
    candidates = info["date_columns"] if info else ["日期", "时间"]
    for candidate in candidates:
        for h in headers:
            if str(h).strip().lower() == candidate.lower():
                return h
    for h in headers:
        if "日" in str(h) or "时" in str(h) or "date" in str(h).lower():
            return h
    return headers[0]

def fetch_oss_token(object_key: str, base_url: str = "") -> str:
    from core.credentials import default_credential_store
    from pathlib import Path
    data = default_credential_store.get(Path(object_key).stem)
    if isinstance(data, dict):
        return data.get("cookie") or data.get("token") or json.dumps(data)
    return str(data)
