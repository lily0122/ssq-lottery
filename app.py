import io
import json
from dataclasses import asdict
from cloud_data import ROOT, official_snapshot, check_update
import pandas as pd
import streamlit as st
from lottery import Params, VERSION, SPACE, REDS, validate, demo, number_stats, generate, walk_forward, fingerprint

@st.cache_data(ttl=3600, max_entries=1, show_spinner=False)
def cached_official_snapshot():
    return official_snapshot()


@st.cache_data(scope='session', max_entries=2, show_spinner=False)
def cached_number_stats(data, short, long, blue):
    return number_stats(data,short,long,blue)

st.set_page_config(page_title='双色球选号实验室',layout='wide')
st.title('双色球选号与数据分析实验室')
st.warning(f'历史规律不提高理论中奖概率。每注一等奖理论概率为 1/{SPACE:,}；评分是规则偏好，不是中奖概率。')
mode=st.sidebar.radio('数据模式',['官方历史数据','导入CSV','模拟演示（非真实开奖）'])
try:
    if mode.startswith('模拟'):
        d=demo(); st.error('当前全部数据为人工随机模拟，仅用于演示和测试，绝非真实开奖记录。')
    elif mode=='导入CSV':
        upload=st.sidebar.file_uploader('上传历史数据',type=['csv'])
        if upload is None:
            st.info('请上传 CSV；字段见下方模板。')
            st.download_button('下载空白CSV模板',(ROOT/'data/import_template.csv').read_bytes(),'import_template.csv'); st.stop()
        if upload.size>5*1024*1024: raise ValueError('CSV文件不能超过5MB')
        raw=upload.getvalue()
        d=pd.read_csv(io.BytesIO(raw),dtype={'issue':str,'date':str},encoding='utf-8-sig')
        st.caption('上传文件仅在本次会话使用；来源字段由提供者填写，不等于官方认证。')
    else:
        path=ROOT/'data/official.csv'
        if not path.exists():
            st.info('尚无内置官方数据，请上传历史CSV或使用模拟演示。'); st.stop()
        d=pd.read_csv(path,dtype={'issue':str,'date':str},encoding='utf-8-sig')
    if mode=='官方历史数据':
        st.sidebar.caption('内置数据可离线使用；按需检查官方更新，成功结果缓存1小时。')
        if st.sidebar.button('检查官方更新', key='refresh_official'):
            try:
                with st.spinner('正在读取并校验官方数据，最多约2分钟…'):
                    updated,manifest,archive=cached_official_snapshot()
                    previous=st.session_state.get('official_snapshot')
                    check_update(previous[0] if previous else d,updated)
                st.session_state['official_snapshot']=(updated,manifest,archive)
                st.sidebar.success('已采用官方返回的最新可用数据')
            except Exception:
                st.sidebar.warning('暂时无法取得完整且一致的官方数据，继续使用现有数据。可稍后重试或导入CSV。')
        snapshot=st.session_state.get('official_snapshot')
        if snapshot:
            d,manifest,archive=snapshot
            st.sidebar.caption(f"采集时间（UTC）：{manifest['retrieved_at_utc']}")
            st.sidebar.download_button('下载更新数据与来源档案',archive,'official-update.zip',on_click='ignore')
        st.sidebar.caption('网页更新用于当前会话；重启后内置数据仍以GitHub中的文件为准。')
    if len(d)>20000: raise ValueError('公开版最多支持20000期数据')
    d,warnings=validate(d)
except Exception as e:
    st.error(f'数据未通过校验：{e}'); st.stop()
st.caption(f'已载入 {len(d)} 期：{d.issue.iloc[0]} 至 {d.issue.iloc[-1]}，日期 {d.date.iloc[0]} 至 {d.date.iloc[-1]}')
with st.expander('数据来源与完整性检查'):
    for msg in warnings: st.write(msg)
    st.write('来源',d.source.unique().tolist()); st.code(fingerprint(d),language=None)
    st.dataframe(d,width='stretch')
    st.download_button('导出规范数据',d.to_csv(index=False).encode('utf-8-sig'),'validated.csv')
cutoff=st.sidebar.selectbox('分析/选号数据截止期',d.issue.tolist(),index=len(d)-1)
d=d[d.issue<=cutoff].reset_index(drop=True)
short=st.sidebar.number_input('短期窗口（期）',1,500,30)
long=st.sidebar.number_input('长期窗口（0=全部已知历史）',0,10000,0)
pool=st.sidebar.select_slider('选号候选池',options=[1000,10000,50000,100000],value=100000)
seed=st.sidebar.number_input('随机种子',0,4294967295,20261110)
st.sidebar.caption('E综合权重：自动归一化')
w=tuple(st.sidebar.number_input(label,0.0,10.0,value,0.05) for label,value in [('结构权重',0.35),('频率遗漏权重',0.35),('期际权重',0.30)])
p=Params(seed=int(seed),pool=int(pool),short=int(short),long=int(long),weights=w)
try:
    p.check()
    if p.pool>100000: raise ValueError('公开版选号候选池上限10万')
except ValueError as e: st.error(str(e)); st.stop()
analysis,picks,bt=st.tabs(['历史分析','五种策略选号','严格顺序回测'])
with analysis:
    st.caption('频率分母为窗口内期数；红球单号码理论频率6/33，蓝球1/16。遗漏未出现时仅表示样本内下界。')
    for blue,label in [(False,'红球'),(True,'蓝球')]:
        st.subheader(label)
        stats=cached_number_stats(d,p.short,p.long,blue)
        st.bar_chart(stats.set_index('号码')[['长期频率','短期频率']])
        st.dataframe(stats,width='stretch')
    red=d[REDS]
    structure=pd.DataFrame({'日期':d.date,'和值':red.sum(axis=1),'奇数个数':(red%2).sum(axis=1),'连号对数':(red.diff(axis=1).iloc[:,1:]==1).sum(axis=1),'低区':(red<=11).sum(axis=1),'中区':((red>11)&(red<=22)).sum(axis=1),'高区':(red>22).sum(axis=1)})
    st.dataframe(structure,width='stretch')
with picks:
    st.caption('A 独立均匀随机；B/C/D/E共用候选池。每种策略内部5注不同，策略之间允许重合。')
    if st.button('生成25注',type='primary',key='generate_tickets'):
        try:
            with st.spinner('正在生成候选并评分…'): result,meta=generate(d,p)
            st.session_state['selection']=(fingerprint(d),p,result,meta)
        except Exception as e: st.error(str(e))
    saved=st.session_state.get('selection')
    if saved and saved[0]==fingerprint(d) and saved[1]==p:
        result,meta=saved[2:]
        for strategy in 'ABCDE':
            st.subheader(f'策略 {strategy}')
            st.dataframe(result[result['策略']==strategy],hide_index=True,width='stretch')
        st.write('跨策略重复完整号码数：',int(result.duplicated(['红球','蓝球']).sum()))
        st.download_button('下载号码、分数及理由CSV',result.to_csv(index=False).encode('utf-8-sig'),'tickets.csv')
        st.download_button('下载完整复现记录JSON',json.dumps({'metadata':meta,'tickets':json.loads(result.to_json(orient='records',force_ascii=False))},ensure_ascii=False,indent=2),'selection.json')
        st.json(meta)
with bt:
    st.info('每个目标期只使用之前的历史。A为同成本随机基准。每策略每期5注（10元）；只统计命中和奖级，不估算浮动奖金或收益。单次随机基准及小样本差异不能证明优势。')
    warm=st.number_input('最少训练期数',2,10000,50)
    limit=st.number_input('回测最近多少期',1,100,30)
    bp=st.select_slider('回测候选池（控制耗时）',[1000,5000,10000],value=1000)
    st.caption('回测独立记录候选池参数；缩小候选池会改变B~E结果。缺期不补造，相邻指已导入记录中的相邻期。')
    bt_key=(fingerprint(d),p,int(warm),int(limit),int(bp))
    if st.button('执行回测',key='run_backtest'):
        try:
            if not 1<=int(limit)<=100 or int(bp) not in (1000,5000,10000):
                raise ValueError('公开版回测最多100期，候选池上限1万')
            q=Params(seed=p.seed,pool=int(bp),short=p.short,long=p.long,weights=p.weights)
            with st.spinner('按时间逐期计算…'): summary,detail=walk_forward(d,q,int(warm),int(limit))
            meta={'version':VERSION,'params':asdict(q),'warmup':warm,'limit':limit,'data_sha256':fingerprint(d),'cutoff':d.issue.iloc[-1],'sources':d.source.unique().tolist(),'numpy':__import__('numpy').__version__,'pandas':pd.__version__}
            st.session_state['backtest']=(bt_key,summary,detail,meta)
        except Exception as e: st.error(str(e))
    saved_bt=st.session_state.get('backtest')
    if saved_bt and saved_bt[0]==bt_key:
        _,summary,detail,meta=saved_bt
        st.dataframe(summary,width='stretch')
        st.caption('理论每注平均红球命中36/33≈1.091，蓝球命中率1/16。')
        st.dataframe(detail,width='stretch')
        st.download_button('下载回测逐注明细',detail.to_csv(index=False).encode('utf-8-sig'),'backtest.csv',on_click='ignore')
        st.download_button('下载回测复现记录',json.dumps(meta,ensure_ascii=False,indent=2),'backtest_metadata.json',on_click='ignore')
