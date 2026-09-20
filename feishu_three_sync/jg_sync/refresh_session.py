"""Renew the report session through a dedicated persistent Chrome profile."""
import json
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent
ACCOUNT='659e1399096eae00013086d6'
URL=f'https://ad.xiaohongshu.com/aurora/ad/datareports-basic/note?vSellerId={ACCOUNT}'


def refresh(interactive=False):
    file=ROOT/'session_headers.json'
    headers=json.loads(file.read_text(encoding='utf-8'))
    profile=ROOT/'.report-profile'
    marker=profile/'.initialized'
    state_file=ROOT/'browser_state.json'
    with sync_playwright() as p:
        context=p.chromium.launch_persistent_context(str(profile),channel='chrome',headless=not interactive)
        try:
            if state_file.exists():
                state=json.loads(state_file.read_text(encoding='utf-8'))
                context.add_cookies(state.get('cookies',[]))
            else:
                cookies=[]
                for item in headers['cookie'].split(';'):
                    if '=' not in item:continue
                    name,value=item.strip().split('=',1)
                    cookies.append({'name':name,'value':value,'url':'https://ad.xiaohongshu.com/'})
                context.add_cookies(cookies)
            page=context.pages[0] if context.pages else context.new_page()
            page.goto(URL,wait_until='domcontentloaded',timeout=60000)
            page.wait_for_timeout(8000)
            if interactive:
                print('请完成聚光登录，验证成功后窗口自动关闭。',flush=True)
            for attempt in range(120 if interactive else 1):
                result=page.evaluate('''async ({account,day}) => {
                  const r=await fetch('/api/leona/rtb/common/data/report', {
                    method:'POST', credentials:'include', headers:{'Content-Type':'application/json','v-seller-id':account},
                    body:JSON.stringify({pageNum:1,pageSize:1,sorts:[],filters:[],dataCaliber:0,timeUnit:'DAY',splitColumns:['placement'],startDate:day,endDate:day,webModule:'base_report_page',dataSource:'account',dataPattern:'table',columns:['time','placement','fee']})});
                  try {const d=await r.json();return {success:d.success,code:d.code,msg:d.msg};}
                  catch {return {success:false,msg:'登录会话不可用'};}
                }''',{'account':ACCOUNT,'day':(date.today()-timedelta(days=1)).isoformat()})
                if result.get('success') is True:
                    cookies=context.cookies(['https://ad.xiaohongshu.com/'])
                    headers['cookie']='; '.join(c['name']+'='+c['value'] for c in cookies)
                    headers['referer']=URL
                    tmp=file.with_suffix('.tmp');tmp.write_text(json.dumps(headers,ensure_ascii=False),encoding='utf-8');tmp.replace(file)
                    context.storage_state(path=str(state_file))
                    marker.write_text('Browser-managed login session.\n',encoding='utf-8')
                    print('聚光浏览器登录有效，当前会话已自动更新。',flush=True)
                    return
                if interactive:page.wait_for_timeout(5000)
            raise RuntimeError('聚光登录已失效，需要运行 refresh_session.py --login 完成一次登录；无需手工复制Cookie。')
        finally:
            context.close()


if __name__=='__main__':
    import sys
    refresh('--login' in sys.argv)
