"""Explicit CLI download. Never silently substitutes sample data."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import requests
import pandas as pd
from lottery import COLUMNS, validate

URL='https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice'

def fetch(output='data/official.csv', max_seconds=120):
    deadline=time.monotonic()+max_seconds
    out=Path(output); out.parent.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    raw=out.parent/('raw_'+stamp); raw.mkdir(exist_ok=True)
    session=requests.Session()
    session.headers.update({'User-Agent':'Mozilla/5.0','Referer':'https://www.cwl.gov.cn/ygkj/wqkjgg/ssq/'})
    rows=[]; pages=None; seen=set(); artifacts=[]
    for page in range(1,501):
        params={'name':'ssq','dayStart':'2003-02-16','dayEnd':datetime.now(timezone.utc).strftime('%Y-%m-%d'),'pageNo':page,'pageSize':100,'systemType':'PC'}
        remaining=deadline-time.monotonic()
        if remaining <= 0: raise TimeoutError('采集超过总时间限制，请稍后重试')
        response=session.get(URL,params=params,timeout=min(15,remaining))
        response.raise_for_status()
        path=raw/f'page_{page}.json'; path.write_bytes(response.content)
        artifacts.append({'file':str(path),'sha256':hashlib.sha256(response.content).hexdigest(),'url':response.url})
        data=response.json()
        if str(data.get('state'))!='0' or not isinstance(data.get('result'),list):
            raise ValueError('官方接口结构/状态异常，原始响应已保留；未发布CSV')
        if pages is None:
            pages=int(data.get('pageCount',data.get('pageNum')))
            if not 1<=pages<=500: raise ValueError('异常页数')
        if int(data.get('pageCount',data.get('pageNum')))!=pages: raise ValueError('采集期间页数变化，请稍后重试')
        result=data['result']
        if not result: raise ValueError('意外空页，无法确认完整性')
        for item in result:
            issue=str(item['code'])
            if issue in seen: raise ValueError('分页重复/数据更新，终止以避免缺期')
            seen.add(issue)
            red=[int(x) for x in item['red'].split(',')]
            if len(red)!=6: raise ValueError('红球字段异常')
            rows.append([issue,str(item['date'])[:10],*red,int(item['blue']),response.url])
        if page>=pages: break
        time.sleep(0.3)
    if len(rows)!=int(data['total']): raise ValueError('返回总数与分页采集数不符')
    frame,warnings=validate(pd.DataFrame(rows,columns=COLUMNS))
    manifest={'retrieved_at_utc':stamp,'source':URL,'requested_start':'2003-02-16','pages':pages,'rows':len(frame),'first_issue':frame.issue.iloc[0],'last_issue':frame.issue.iloc[-1],'warnings':warnings,'raw':artifacts,'completeness':'仅为接口此次返回范围，不保证全历史完整'}
    content=frame.to_csv(index=False).encode('utf-8-sig')
    manifest['csv_sha256']=hashlib.sha256(content).hexdigest()
    temp=out.with_suffix('.tmp'); temp.write_bytes(content); temp.replace(out)
    out.with_suffix('.provenance.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'已保存 {len(frame)} 期至 {out}；请查看 provenance 文件和缺期提示。')

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',default='data/official.csv'); args=parser.parse_args()
    try: fetch(args.output)
    except Exception as e: raise SystemExit(f'采集失败：{e}。不生成替代真实数据；请使用CSV导入或模拟演示。')
