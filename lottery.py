"""Pure selection and walk-forward engine. Scores are preferences, never probabilities."""
from dataclasses import dataclass, asdict
from math import comb
import hashlib
import json
import numpy as np
import pandas as pd

VERSION = "1.0.0"
REDS = [f"red_{i}" for i in range(1, 7)]
COLUMNS = ["issue", "date", *REDS, "blue", "source"]
SPACE = comb(33, 6) * 16

@dataclass(frozen=True)
class Params:
    seed: int = 20261110
    pool: int = 100000
    short: int = 30
    long: int = 0  # zero = all available past
    weights: tuple = (0.35, 0.35, 0.30)

    def check(self):
        if not 5 <= self.pool <= 500000 or self.short < 1 or self.long < 0:
            raise ValueError("候选池需为5~500000，窗口必须有效")
        if self.long and self.long < self.short:
            raise ValueError("长期窗口不能小于短期窗口")
        if len(self.weights) != 3 or not np.isfinite(self.weights).all() or min(self.weights) < 0 or sum(self.weights) <= 0:
            raise ValueError("综合权重需为三个非负数且总和大于零")

def validate(frame, today=None):
    missing = set(COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"缺少列：{sorted(missing)}")
    d = frame[COLUMNS].copy()
    if d.empty or d.isna().any().any():
        raise ValueError("数据为空或含空字段")
    d['issue'] = d.issue.astype(str).str.strip()
    if not d.issue.str.fullmatch(r'\d{7}').all() or (d.issue.str[4:].astype(int) < 1).any():
        raise ValueError("期号必须为7位 YYYYNNN，序号不能为000")
    if not d.date.astype(str).str.fullmatch(r'\d{4}-\d{2}-\d{2}').all():
        raise ValueError("日期必须为 YYYY-MM-DD")
    dates = pd.to_datetime(d.date, errors='coerce')
    if dates.isna().any() or (dates > pd.Timestamp(today or pd.Timestamp.now(tz='Asia/Shanghai').date())).any() or (dates < '2003-02-16').any():
        raise ValueError("日期无效、早于双色球首期或晚于今天")
    if not (dates.dt.year.astype(str) == d.issue.str[:4]).all():
        raise ValueError("期号年份与日期不一致")
    for c in REDS + ['blue']:
        values = pd.to_numeric(d[c], errors='coerce')
        if not np.isfinite(values).all() or (values != np.floor(values)).any():
            raise ValueError(f"{c} 必须为整数")
        d[c] = values.astype(int)
    r = d[REDS].to_numpy()
    if (r < 1).any() or (r > 33).any() or (np.diff(np.sort(r, axis=1), axis=1) == 0).any() or not d.blue.between(1, 16).all():
        raise ValueError("号码越界或同一期红球重复")
    d[REDS] = np.sort(r, axis=1)
    if d.issue.duplicated().any() or d.date.duplicated().any():
        raise ValueError("存在重复期号或开奖日期（包括冲突记录），请人工核实")
    if d.source.astype(str).str.strip().eq('').any():
        raise ValueError("每条记录必须注明来源")
    d = d.sort_values('date').reset_index(drop=True)
    if not d.issue.is_monotonic_increasing:
        raise ValueError("期号与日期顺序冲突")
    warnings = []
    for year, g in d.groupby(d.issue.str[:4]):
        seq = g.issue.str[4:].astype(int)
        gaps = sorted(set(range(1, int(seq.max())+1)) - set(seq))
        if gaps:
            warnings.append(f"{year} 年内部/年初缺期：{gaps[:30]}（共{len(gaps)}期）；不补造")
    warnings.append("校验不证明来源真实性；范围之外及跨年年末缺期无法自动判断，不能宣称全历史完整。")
    return d, warnings

def demo(n=180):
    rng = np.random.default_rng(42)
    dates = pd.date_range('2020-01-01', periods=n, freq='D')
    rows = [[f'2020{i+1:03d}', str(date.date()), *sorted(rng.choice(np.arange(1,34),6,replace=False)), int(rng.integers(1,17)), 'SYNTHETIC_DEMO_NOT_REAL'] for i,date in enumerate(dates)]
    return pd.DataFrame(rows, columns=COLUMNS)

def sample(rng, n):
    # iid continuous rankings give uniform 6-subsets; independent uniform blue.
    r = np.sort(np.argpartition(rng.random((n,33)), 5, axis=1)[:,:6]+1, axis=1)
    return np.column_stack((r, rng.integers(1,17,n)))

def unique_pool(rng, n):
    out = np.unique(sample(rng,n), axis=0)
    while len(out) < n:
        out = np.unique(np.vstack((out,sample(rng,n-len(out)))),axis=0)
    return out

def number_stats(d, short=30, long=0, blue=False):
    a = d[['blue'] if blue else REDS].to_numpy()
    size, k = (16,1) if blue else (33,6)
    past = a[-long:] if long else a
    counts = np.bincount(past.ravel(),minlength=size+1)[1:]
    recent = np.bincount(a[-short:].ravel(),minlength=size+1)[1:]
    omission = np.array([next((i for i,row in enumerate(a[::-1]) if x in row),len(a)) for x in range(1,size+1)])
    return pd.DataFrame({'号码':np.arange(1,size+1),'长期次数':counts,'短期次数':recent,'长期频率':counts/max(1,len(past)), '短期频率':recent/max(1,min(short,len(a))), '当前遗漏':omission, '未在样本出现':omission==len(a)})

def features(tickets, d, p):
    r,b = tickets[:,:6],tickets[:,6]
    odd = (r%2).sum(axis=1)
    zones = np.column_stack([(r<=11).sum(axis=1),((r>11)&(r<=22)).sum(axis=1),(r>22).sum(axis=1)])
    pairs = (np.diff(r,axis=1)==1).sum(axis=1)
    sums = r.sum(axis=1)
    span = r[:,-1]-r[:,0]
    primes = np.isin(r,[2,3,5,7,11,13,17,19,23,29,31]).sum(axis=1)
    # Exact structure-class masses for odd count / zones. Other preferences are explicit heuristics.
    odd_mass = np.array([comb(17,int(x))*comb(16,6-int(x)) for x in odd],float)
    odd_mass /= max(comb(17,x)*comb(16,6-x) for x in range(7))
    zone_mass = np.array([np.prod([comb(11,int(x)) for x in z]) for z in zones],float)
    zone_mass /= comb(11,2)**3
    balance = 100*(odd_mass+zone_mass+np.exp(-((sums-102)/30)**2)+np.exp(-((span-24)/8)**2)+np.exp(-((pairs-1)/1.5)**2)+np.exp(-((primes-2)/2)**2))/6
    rf=number_stats(d,p.short,p.long); bf=number_stats(d,p.short,p.long,True)
    def frequency(f, idx):
        # Rank normalization is descriptive, 0..100. Omission capped to avoid domination.
        rank=lambda x: pd.Series(x).rank(method='average',pct=True).to_numpy()
        v=(rank(f['长期频率'])+rank(f['短期频率'])+np.minimum(f['当前遗漏'].to_numpy(),30)/30)/3
        return v[idx-1].mean(axis=1) if idx.ndim==2 else v[idx-1]
    freq=100*(0.75*frequency(rf,r)+0.25*frequency(bf,b))
    past=d.iloc[-p.long:] if p.long else d
    a=past[REDS].to_numpy(); blue=past.blue.to_numpy()
    last=d[REDS].iloc[-1].to_numpy()
    repeat=np.isin(r,last).sum(axis=1)
    hist=np.array([len(set(x)&set(y)) for x,y in zip(a[:-1],a[1:])],int)
    dist=np.bincount(hist,minlength=7)+1.0
    rep_score=dist[repeat]/dist.max()
    # Blue Markov row: transitions from last observed blue, add-one smoothing.
    counts=np.ones(16)
    for x,y in zip(blue[:-1],blue[1:]):
        if x==blue[-1]: counts[y-1]+=1
    trans=100*(0.75*rep_score+0.25*counts[b-1]/counts.max())
    w=np.array(p.weights)/sum(p.weights)
    return pd.DataFrame({'B结构分':balance,'C频率遗漏分':freq,'D期际分':trans,'E综合分':w[0]*balance+w[1]*freq+w[2]*trans,'红球和值':sums,'奇数个数':odd,'低区':zones[:,0],'中区':zones[:,1],'高区':zones[:,2],'连号对数':pairs,'跨度':span,'质数个数':primes,'上期重复红球数':repeat,'上期蓝球相同':b==d.blue.iloc[-1]})

def fingerprint(d):
    return hashlib.sha256(d.to_csv(index=False).encode()).hexdigest()

def generate(d,p=Params()):
    p.check()
    if len(d)<2: raise ValueError('至少需要2期历史数据')
    seeds=np.random.SeedSequence(p.seed).spawn(2)
    # A is independent of pool size, uses first-occurrence rejection to stay uniform.
    rng=np.random.default_rng(seeds[0]); chosen=[]
    while len(chosen)<5:
        t=tuple(sample(rng,1)[0])
        if t not in chosen: chosen.append(t)
    base=np.array(chosen)
    pool=unique_pool(np.random.default_rng(seeds[1]),p.pool)
    f=features(pool,d,p); rows=[]
    for name,col in [('A',None),('B','B结构分'),('C','C频率遗漏分'),('D','D期际分'),('E','E综合分')]:
        if name=='A': ts=base; fs=features(ts,d,p)
        else:
            ix=np.argsort(-f[col].to_numpy(),kind='stable')[:5]; ts=pool[ix]; fs=f.iloc[ix].reset_index(drop=True)
        for j,t in enumerate(ts):
            scores=fs.iloc[j].to_dict()
            reason={'A':'均匀随机抽取，不使用评分排序。','B':'优先匹配理论结构类别及明确的结构偏好。','C':'偏好长短期高频及较大遗漏，属于实验性规则。','D':'偏好历史重复红球数量和上期蓝球转移类别。','E':'按所设权重综合结构、频率遗漏、期际分。'}[name]
            rows.append({'策略':name,'注':j+1,'红球':' '.join(f'{x:02d}' for x in t[:6]),'蓝球':int(t[6]),'排序分':None if col is None else float(scores[col]),**scores,'理由':reason+f" 和值{int(scores['红球和值'])}，上期重复{int(scores['上期重复红球数'])}个。评分不是概率。"})
    meta={'algorithm_version':VERSION,'parameters':asdict(p),'data_cutoff_issue':str(d.issue.iloc[-1]),'data_cutoff_date':str(d.date.iloc[-1]),'data_sha256':fingerprint(d),'rows':len(d),'numpy':np.__version__,'pandas':pd.__version__,'tie_break':'候选号码字典序','sources':sorted(d.source.unique().tolist())}
    return pd.DataFrame(rows),meta

def prize(red,blue):
    if red==6: return 1 if blue else 2
    if red==5: return 3 if blue else 4
    if red==4: return 4 if blue else 5
    if red==3 and blue: return 5
    if blue: return 6
    return 0

def walk_forward(d,p=Params(),warmup=50,limit=30):
    if warmup<2 or warmup>=len(d) or limit<1: raise ValueError('回测需要足够历史，训练至少2期')
    rows=[]
    start=max(warmup,len(d)-limit)
    for i in range(start,len(d)):
        # All fitting and previous-draw features see only the prefix.
        q=Params(seed=int(np.random.SeedSequence([p.seed,i]).generate_state(1)[0]),pool=p.pool,short=p.short,long=p.long,weights=p.weights)
        picks,meta=generate(d.iloc[:i],q)
        actual=d.iloc[i]; actual_red=set(actual[REDS].astype(int))
        for _,t in picks.iterrows():
            hits=len(set(map(int,t['红球'].split()))&actual_red); bh=int(t['蓝球']==actual.blue)
            rows.append({'目标期':actual.issue,'训练截止期':meta['data_cutoff_issue'],'训练截止日期':meta['data_cutoff_date'],'seed':q.seed,'策略':t['策略'],'注':t['注'],'红球':t['红球'],'蓝球':t['蓝球'],'红球命中':hits,'蓝球命中':bh,'奖级':prize(hits,bh)})
    detail=pd.DataFrame(rows)
    summary=detail.groupby('策略').agg(注数=('注','size'),平均红球命中=('红球命中','mean'),蓝球命中率=('蓝球命中','mean'),中奖注数=('奖级',lambda x:int((x>0).sum())))
    for k in range(1,7): summary[f'{k}等奖注数']=detail.groupby('策略')['奖级'].apply(lambda x:int((x==k).sum()))
    summary['相对A平均红球差']=summary['平均红球命中']-summary.loc['A','平均红球命中']
    return summary,detail
