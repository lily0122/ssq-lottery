import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import lottery as l

class CoreTests(unittest.TestCase):
    def setUp(self): self.d=l.demo(70)
    def test_math(self):
        self.assertEqual(l.SPACE,17721088)
        from math import comb
        self.assertEqual(sum(comb(6,k)*comb(27,6-k) for k in range(7)),comb(33,6))
        self.assertAlmostEqual(sum(k*comb(6,k)*comb(27,6-k)/comb(33,6) for k in range(7)),36/33)
    def test_validation(self):
        d,w=l.validate(self.d.iloc[::-1]); self.assertEqual(d.issue.iloc[0],'2020001')
        self.assertTrue(w)
        for mutation in ['duplicate','red','range','fraction','date','source','issue']:
            d=self.d.copy()
            if mutation=='duplicate': d=pd.concat([d,d.iloc[:1]])
            elif mutation=='red': d.loc[0,'red_2']=d.loc[0,'red_1']
            elif mutation=='range': d.loc[0,'blue']=17
            elif mutation=='fraction': d['blue']=d.blue.astype(float); d.loc[0,'blue']=1.2
            elif mutation=='date': d.loc[0,'date']='2099-01-01'
            elif mutation=='source': d.loc[0,'source']=''
            elif mutation=='issue': d.loc[0,'issue']='2020000'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError): l.validate(d)
    def test_frequency_omission(self):
        f=l.number_stats(self.d,10)
        self.assertEqual(f['长期次数'].sum(),70*6)
        self.assertEqual(f['短期次数'].sum(),60)
        for x in self.d[l.REDS].iloc[-1]: self.assertEqual(f.loc[x-1,'当前遗漏'],0)
        b=l.number_stats(self.d,10,blue=True)
        self.assertEqual(b['长期次数'].sum(),70)
    def test_generation(self):
        p=l.Params(pool=300)
        a,m=l.generate(self.d,p); b,n=l.generate(self.d,p)
        pd.testing.assert_frame_equal(a,b); self.assertEqual(m,n)
        for _,g in a.groupby('策略'):
            self.assertEqual(len(g),5); self.assertFalse(g.duplicated(['红球','蓝球']).any())
            for _,row in g.iterrows():
                r=list(map(int,row['红球'].split()))
                self.assertEqual(len(set(r)),6); self.assertTrue(all(1<=x<=33 for x in r)); self.assertTrue(1<=row['蓝球']<=16)
        self.assertTrue(a[['B结构分','C频率遗漏分','D期际分','E综合分']].apply(lambda s:s.between(0,100)).all().all())
        larger,_=l.generate(self.d,l.Params(pool=400))
        pd.testing.assert_frame_equal(a[a['策略']=='A'],larger[larger['策略']=='A'])
    def test_prizes(self):
        expected={(6,1):1,(6,0):2,(5,1):3,(5,0):4,(4,1):4,(4,0):5,(3,1):5,(3,0):0,(2,1):6,(1,1):6,(0,1):6,(2,0):0}
        for pair,level in expected.items(): self.assertEqual(l.prize(*pair),level)
    def test_walk_forward_prefix_only(self):
        original=l.generate; calls=[]
        def spy(d,p):
            calls.append(d.copy()); return original(d,p)
        with patch('lottery.generate',side_effect=spy):
            summary,detail=l.walk_forward(self.d,l.Params(pool=30),warmup=50,limit=3)
        self.assertEqual([len(x) for x in calls],[67,68,69])
        self.assertTrue((detail['训练截止期']<detail['目标期']).all())
        self.assertEqual(len(detail),75); self.assertTrue((summary['注数']==15).all())
        pd.testing.assert_frame_equal(calls[0],self.d.iloc[:67])
        altered=self.d.copy(); altered.loc[69,'blue']=16
        _,a=l.walk_forward(altered,l.Params(pool=30),50,3)
        pd.testing.assert_frame_equal(detail[['红球','蓝球','seed']],a[['红球','蓝球','seed']])
    def test_bad_parameters(self):
        for p in [l.Params(pool=4),l.Params(short=30,long=10),l.Params(weights=(0,0,0))]:
            with self.assertRaises(ValueError): p.check()

if __name__=='__main__': unittest.main()
