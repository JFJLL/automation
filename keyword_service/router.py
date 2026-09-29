import os
import sys
import json
import hmac
from pathlib import Path
from typing import Optional, List, Union
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from keyword_service.client import fetch_keywords_insight, load_token
from keyword_service.db import get_db, init_db
from keyword_service.sync_engine import (
    direct_create_feishu_sheet,
    create_keyword_task,
    run_keyword_task,
    append_keywords_to_task,
    remove_keywords_from_task
)
from keyword_service.scheduler import init_keyword_scheduler, reschedule_keyword_task, remove_keyword_job
from app.config import ACCESS_TOKEN

router = APIRouter()

private_router = APIRouter(prefix="/api/keyword")
HTML_PATH = Path(__file__).parent / "templates" / "keyword.html"
KEYWORD_LIBRARY_PATH = Path(__file__).parent / "all_keyword_trends.json"

# 初始化数据库
init_db()

class KeywordSearchRequest(BaseModel):
    keywords: Union[str, List[str]]
    start_date: Optional[str] = None
    end_date: Optional[str] = None

class DirectSheetRequest(BaseModel):
    title: Optional[str] = None
    keywords: List[str]
    start_date: Optional[str] = None
    end_date: Optional[str] = None

class CreateKeywordTaskRequest(BaseModel):
    task_name: str
    keywords: List[str]
    update_mode: str = "overwrite" # 'overwrite' 或 'append'
    rrule: str = "FREQ=DAILY;BYHOUR=12;BYMINUTE=30"
    days_range: int = 90

class AppendKeywordsRequest(BaseModel):
    keywords: Union[str, List[str]]
    sync_now: bool = True

class RemoveKeywordsRequest(BaseModel):
    keywords: Union[str, List[str]]

class KeywordLoginRequest(BaseModel):
    password: str

@router.get("/keyword", response_class=HTMLResponse)
def keyword_page():
    if not HTML_PATH.exists():
        raise HTTPException(status_code=404, detail="Page template not found")
    return HTMLResponse(content=HTML_PATH.read_text(encoding="utf-8"))

@router.get("/api/keyword/library")
def keyword_library():
    """Return the keyword library as a two-level taxonomy for UI filtering."""
    if not KEYWORD_LIBRARY_PATH.exists():
        return {"groups": [], "total": 0}

    try:
        data = json.loads(KEYWORD_LIBRARY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"关键词库读取失败: {exc}")

    outdoor_keywords = list(data.keys())

    def words(value):
        return [item.strip() for item in value.split("|") if item.strip()]

    def contains_any(keyword, terms):
        lower = keyword.lower()
        return any(term.lower() in lower for term in terms)

    def unique(items):
        return list(dict.fromkeys(items))

    curated_groups = [
        {
            "name": "母婴",
            "subcategories": [
                {"name": "奶粉喂养", "keywords": words("婴儿奶粉|新生儿奶粉|一段奶粉|二段奶粉|三段奶粉|羊奶粉|奶粉测评|奶粉怎么选|宝宝不喝奶粉|转奶攻略")},
                {"name": "纸尿裤", "keywords": words("纸尿裤|拉拉裤|新生儿纸尿裤|纸尿裤推荐|纸尿裤测评|轻薄纸尿裤|透气纸尿裤|夜用拉拉裤|纸尿裤红屁屁|纸尿裤囤货")},
                {"name": "辅食营养", "keywords": words("宝宝辅食|婴儿米粉|宝宝零食|婴幼儿益生菌|儿童钙铁锌|宝宝辅食机|辅食添加顺序|一岁宝宝食谱|宝宝营养餐|儿童维生素")},
                {"name": "洗护用品", "keywords": words("婴儿面霜|宝宝洗发沐浴露|婴儿润肤乳|宝宝防晒|婴儿湿巾|宝宝护臀膏|婴儿洗衣液|宝宝驱蚊|婴儿抚触油|母婴洗护")},
                {"name": "出行寝居", "keywords": words("婴儿车|安全座椅|婴儿床|宝宝餐椅|婴儿背带|恒温水壶|奶瓶消毒柜|婴儿睡袋|宝宝床品|母婴包")},
                {"name": "孕产护理", "keywords": words("孕妇护肤|孕妇装|待产包|产后修复|哺乳内衣|吸奶器|储奶袋|月子用品|妊娠纹护理|孕期营养")},
            ],
        },
        {
            "name": "美妆护肤",
            "subcategories": [
                {"name": "防晒", "keywords": words("防晒霜|防晒推荐|油皮防晒|敏感肌防晒|通勤防晒|户外防晒|防晒喷雾|防晒测评|不搓泥防晒|身体防晒")},
                {"name": "精华面霜", "keywords": words("精华液|抗老精华|美白精华|修护精华|面霜推荐|敏感肌面霜|油皮面霜|抗老面霜|早c晚a|屏障修护")},
                {"name": "面膜洁面", "keywords": words("面膜推荐|补水面膜|清洁面膜|睡眠面膜|敏感肌面膜|洗面奶|氨基酸洗面奶|卸妆油|卸妆膏|毛孔清洁")},
                {"name": "彩妆", "keywords": words("粉底液|持妆粉底液|气垫推荐|口红色号|腮红推荐|眼影盘|睫毛膏|遮瑕推荐|定妆喷雾|新手化妆")},
                {"name": "香水个护", "keywords": words("香水推荐|女生香水|男士香水|留香持久香水|洗发水推荐|护发精油|身体乳|止汗露|头皮护理|香氛沐浴露")},
                {"name": "肤质问题", "keywords": words("油皮护肤|干皮护肤|敏感肌护肤|痘肌护肤|毛孔粗大|闭口粉刺|黑头清洁|皮肤暗沉|换季过敏|熬夜护肤")},
            ],
        },
        {
            "name": "户外运动",
            "subcategories": [
                {"name": "户外热门词", "keywords": outdoor_keywords},
                {"name": "冲锋衣", "keywords": [kw for kw in outdoor_keywords if "冲锋衣" in kw]},
                {"name": "户外品牌", "keywords": [kw for kw in outdoor_keywords if contains_any(kw, ["凯乐石", "kailas", "狼爪", "jackwolfskin", "北面", "thenorthface", "伯希和", "始祖鸟", "骆驼", "迪卡侬"])]},
                {"name": "鞋服装备", "keywords": [kw for kw in outdoor_keywords if contains_any(kw, ["鞋", "背包", "登山包", "软壳", "硬壳", "羽绒服", "裤子", "帽"])]},
                {"name": "露营徒步", "keywords": words("露营装备|露营帐篷|天幕推荐|露营桌椅|睡袋推荐|徒步装备|登山杖|户外水壶|徒步路线|轻量化露营|自驾露营|户外炉具")},
                {"name": "跑步健身", "keywords": words("跑步鞋|越野跑鞋|跑步装备|运动手表|健身穿搭|瑜伽服|运动内衣|筋膜枪|居家健身|减脂运动|力量训练|跑步入门")},
            ],
        },
        {
            "name": "服饰鞋包",
            "subcategories": [
                {"name": "女装穿搭", "keywords": words("秋冬穿搭|小个子穿搭|通勤穿搭|显瘦穿搭|法式穿搭|新中式穿搭|毛衣推荐|大衣穿搭|羽绒服穿搭|裙子推荐")},
                {"name": "男装", "keywords": words("男生穿搭|男士外套|男士羽绒服|男士卫衣|男士衬衫|男士休闲裤|男士西装|男生通勤穿搭|男装品牌|男士基础款")},
                {"name": "鞋靴", "keywords": words("运动鞋推荐|小白鞋|跑鞋推荐|短靴穿搭|乐福鞋|老爹鞋|通勤鞋|厚底鞋|雪地靴|鞋子测评")},
                {"name": "箱包配饰", "keywords": words("通勤包|双肩包推荐|腋下包|托特包|旅行箱|斜挎包|帽子穿搭|围巾推荐|首饰搭配|平价包包")},
            ],
        },
        {
            "name": "食品饮料",
            "subcategories": [
                {"name": "休闲零食", "keywords": words("零食推荐|办公室零食|低卡零食|追剧零食|儿童零食|坚果推荐|肉脯推荐|饼干推荐|巧克力推荐|年货零食")},
                {"name": "咖啡茶饮", "keywords": words("咖啡豆推荐|挂耳咖啡|速溶咖啡|冷萃咖啡|咖啡机|茶包推荐|养生茶|无糖饮料|气泡水|奶茶推荐")},
                {"name": "健康轻食", "keywords": words("低脂早餐|减脂餐|全麦面包|代餐推荐|即食鸡胸肉|燕麦推荐|控糖食品|高蛋白零食|轻食沙拉|健康饮食")},
                {"name": "地方特产", "keywords": words("地方特产|伴手礼推荐|特产零食|中秋礼盒|春节礼盒|送礼推荐|家乡美食|网红美食|老字号美食|城市伴手礼")},
            ],
        },
        {
            "name": "家居生活",
            "subcategories": [
                {"name": "清洁收纳", "keywords": words("收纳好物|衣柜收纳|厨房收纳|小户型收纳|清洁好物|洗衣液推荐|扫地机器人|吸尘器推荐|除螨仪|卫生间清洁")},
                {"name": "厨房用品", "keywords": words("空气炸锅|破壁机|电饭煲推荐|咖啡机推荐|不粘锅|保温杯|厨房好物|烘焙工具|净水器|洗碗机")},
                {"name": "床品家纺", "keywords": words("四件套推荐|床垫推荐|枕头推荐|被子推荐|乳胶枕|羽绒被|儿童床品|凉席推荐|家居服|睡眠好物")},
                {"name": "装修软装", "keywords": words("装修避坑|客厅软装|卧室改造|小户型装修|租房改造|灯具推荐|窗帘搭配|沙发推荐|餐桌推荐|家居配色")},
            ],
        },
        {
            "name": "数码家电",
            "subcategories": [
                {"name": "手机数码", "keywords": words("手机推荐|拍照手机|手机测评|平板电脑|智能手表|蓝牙耳机|充电宝|手机壳|数码好物|学生平板")},
                {"name": "电脑办公", "keywords": words("笔记本电脑推荐|轻薄本|游戏本|机械键盘|显示器推荐|办公好物|打印机|人体工学椅|移动硬盘|电脑支架")},
                {"name": "生活家电", "keywords": words("洗衣机推荐|冰箱推荐|空调推荐|电视推荐|烘干机|智能门锁|除湿机|空气净化器|电风扇|取暖器")},
                {"name": "影音娱乐", "keywords": words("投影仪推荐|蓝牙音箱|家庭影院|游戏机|掌机推荐|麦克风|运动相机|相机推荐|拍立得|无人机")},
            ],
        },
    ]

    result_groups = []
    all_keywords = []
    for group in curated_groups:
        subcategories = []
        group_keywords = []
        for subcategory in group["subcategories"]:
            sub_keywords = unique(subcategory["keywords"])
            if sub_keywords:
                subcategories.append({"name": subcategory["name"], "keywords": sub_keywords})
                group_keywords.extend(sub_keywords)
        group_keywords = unique(group_keywords)
        all_keywords.extend(group_keywords)
        result_groups.append({
            "name": group["name"],
            "count": len(group_keywords),
            "subcategories": subcategories,
        })

    all_keywords = unique(all_keywords)
    return {"groups": result_groups, "all_keywords": all_keywords, "total": len(all_keywords)}

@router.get("/favicon.svg")
def keyword_favicon_svg():
    candidates = [
        Path(__file__).parent.parent / "sync_console" / "web" / "favicon.svg",
        Path(__file__).parent.parent / "web" / "favicon.svg"
    ]
    for p in candidates:
        if p.exists():
            return Response(content=p.read_bytes(), media_type="image/svg+xml")
    return Response(status_code=404)

@router.get("/favicon.ico")
def keyword_favicon_ico():
    candidates = [
        Path(__file__).parent.parent / "sync_console" / "web" / "favicon.ico",
        Path(__file__).parent.parent / "web" / "favicon.ico"
    ]
    for p in candidates:
        if p.exists():
            return Response(content=p.read_bytes(), media_type="image/x-icon")
    return keyword_favicon_svg()

@private_router.post("/search")
def search_keywords(req: KeywordSearchRequest):
    if isinstance(req.keywords, str):
        kw_list = [w.strip() for w in req.keywords.split() if w.strip()]
    else:
        kw_list = [w.strip() for w in req.keywords if w.strip()]
        
    if not kw_list:
        raise HTTPException(status_code=400, detail="关键词不能为空，请至少输入一个关键词")
        
    try:
        data = fetch_keywords_insight(
            keywords=kw_list,
            start_date=req.start_date,
            end_date=req.end_date
        )
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.post("/feishu/direct_create")
def create_feishu_sheet_directly(req: DirectSheetRequest):
    if not req.keywords:
        raise HTTPException(status_code=400, detail="关键词列表不能为空")
    try:
        res = direct_create_feishu_sheet(
            keywords=req.keywords,
            start_date=req.start_date,
            end_date=req.end_date,
            title=req.title
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.get("/tasks")
def list_keyword_tasks():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM keyword_tasks WHERE status != 'archived' ORDER BY id DESC")
        tasks = []
        for r in cursor.fetchall():
            item = dict(r)
            item["keywords"] = json.loads(item.get("keywords_json") or "[]")
            item["removed_keywords"] = json.loads(item.get("removed_keywords_json") or "[]")
            tasks.append(item)
    return tasks

@private_router.post("/tasks")
def add_keyword_task(req: CreateKeywordTaskRequest):
    if not req.keywords:
        raise HTTPException(status_code=400, detail="任务至少需要包含一个关键词")
    try:
        res = create_keyword_task(
            task_name=req.task_name,
            keywords=req.keywords,
            update_mode=req.update_mode,
            rrule_str=req.rrule,
            days_range=req.days_range
        )
        reschedule_keyword_task(res["task_id"])
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.post("/tasks/{task_id}/append_keywords")
def append_words_endpoint(task_id: int, req: AppendKeywordsRequest):
    if isinstance(req.keywords, str):
        kw_list = [w.strip() for w in req.keywords.split() if w.strip()]
    else:
        kw_list = [w.strip() for w in req.keywords if w.strip()]
        
    if not kw_list:
        raise HTTPException(status_code=400, detail="请至少输入一个要添加的关键词")
        
    try:
        res = append_keywords_to_task(task_id, kw_list, sync_now=req.sync_now)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.post("/tasks/{task_id}/remove_keywords")
def remove_words_endpoint(task_id: int, req: RemoveKeywordsRequest):
    if isinstance(req.keywords, str):
        kw_list = [w.strip() for w in req.keywords.split() if w.strip()]
    else:
        kw_list = [w.strip() for w in req.keywords if w.strip()]
        
    if not kw_list:
        raise HTTPException(status_code=400, detail="请至少提供一个要减掉的关键词")
        
    try:
        res = remove_keywords_from_task(task_id, kw_list)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.post("/tasks/{task_id}/run_now")
def run_task_immediately(task_id: int):
    try:
        res = run_keyword_task(task_id, trigger_type="manual")
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.post("/tasks/{task_id}/toggle")
def toggle_task(task_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM keyword_tasks WHERE id = ?", (task_id,))
        r = cursor.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Task not found")
        new_status = "paused" if r["status"] == "active" else "active"
        conn.execute("UPDATE keyword_tasks SET status = ?, updated_at = ? WHERE id = ?", (new_status, datetime.now().isoformat(), task_id))
        conn.commit()
        
    reschedule_keyword_task(task_id)
    return {"status": new_status}

@private_router.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM keyword_tasks WHERE id = ?", (task_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Task not found")
        conn.execute("UPDATE keyword_tasks SET status = 'archived', updated_at = ? WHERE id = ?", (datetime.now().isoformat(), task_id))
        conn.commit()
    remove_keyword_job(task_id)
    return {"success": True, "message": f"任务 #{task_id} 已成功删除"}

@private_router.get("/runs")
def list_keyword_runs(task_id: Optional[int] = None, page: int = 1, page_size: int = 20):
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20
    offset = (page - 1) * page_size

    with get_db() as conn:
        cursor = conn.cursor()
        if task_id:
            cursor.execute("SELECT COUNT(*) FROM keyword_runs WHERE task_id = ?", (task_id,))
            total = cursor.fetchone()[0]
            cursor.execute("SELECT * FROM keyword_runs WHERE task_id = ? ORDER BY id DESC LIMIT ? OFFSET ?", (task_id, page_size, offset))
        else:
            cursor.execute("SELECT COUNT(*) FROM keyword_runs")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT * FROM keyword_runs ORDER BY id DESC LIMIT ? OFFSET ?", (page_size, offset))
        runs = [dict(r) for r in cursor.fetchall()]

    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "items": runs,
        "total": total,
        "total_pages": total_pages,
        "page": page,
        "page_size": page_size
    }

router.include_router(private_router)

# 允许作为独立应用启动
app = FastAPI(title="关键词搜索指数服务")
app.include_router(router)

@app.post("/api/auth/login")
def standalone_login(req: KeywordLoginRequest, response: Response):
    if not hmac.compare_digest(req.password, ACCESS_TOKEN):
        raise HTTPException(status_code=401, detail="密码错误")
    response.set_cookie("access_token", ACCESS_TOKEN, max_age=86400, httponly=True, samesite="lax")
    return {"success": True}

@app.on_event("startup")
def on_startup():
    init_keyword_scheduler()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8090)

