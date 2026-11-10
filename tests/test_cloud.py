import unittest
from unittest.mock import patch
import pandas as pd
from cloud_data import check_update
from lottery import demo, validate

class CloudDataTests(unittest.TestCase):
    def test_only_consistent_superset_allowed(self):
        d,_=validate(demo(10))
        check_update(d.iloc[:5],d)
        with self.assertRaises(ValueError): check_update(d,d.iloc[:5])
        changed=d.copy(); changed.loc[0,'blue']=1 if d.blue.iloc[0]!=1 else 2
        with self.assertRaises(ValueError): check_update(d,changed)

class WebsiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:
            raise unittest.SkipTest('Install requirements.txt to run UI tests')
        cls.AppTest=AppTest

    def test_sessions_and_backtest_persistence(self):
        from pathlib import Path
        path=str(Path(__file__).resolve().parents[1]/'app.py')
        a=self.AppTest.from_file(path,default_timeout=30).run()
        self.assertFalse(a.exception)
        a.button(key='generate_tickets').click().run()
        self.assertFalse(a.exception)
        self.assertEqual(len(a.session_state['selection'][2]),25)
        b=self.AppTest.from_file(path,default_timeout=30).run()
        self.assertNotIn('selection',b.session_state)
        a.button(key='run_backtest').click().run()
        self.assertFalse(a.exception)
        self.assertEqual(len(a.session_state['backtest'][2]),750)
        a.run()
        self.assertEqual(len(a.session_state['backtest'][2]),750)
        self.assertNotIn('backtest',b.session_state)

    def test_failed_update_keeps_bundled_data(self):
        from pathlib import Path
        path=str(Path(__file__).resolve().parents[1]/'app.py')
        with patch('cloud_data.official_snapshot',side_effect=RuntimeError('offline')):
            a=self.AppTest.from_file(path,default_timeout=30).run()
            a.button(key='refresh_official').click().run()
        self.assertFalse(a.exception)
        self.assertTrue(any('继续使用现有数据' in x.value for x in a.warning))
        self.assertNotIn('official_snapshot',a.session_state)

    def test_successful_update_is_session_local(self):
        from pathlib import Path
        from lottery import validate
        root=Path(__file__).resolve().parents[1]
        frame,_=validate(pd.read_csv(root/'data/official.csv',dtype={'issue':str,'date':str}))
        before=(root/'data/official.csv').read_bytes()
        with patch('cloud_data.official_snapshot',return_value=(frame,{'retrieved_at_utc':'20261110T120000Z'},b'archive')):
            a=self.AppTest.from_file(str(root/'app.py'),default_timeout=30).run()
            a.button(key='refresh_official').click().run()
            self.assertFalse(a.exception)
            self.assertEqual(len(a.session_state['official_snapshot'][0]),len(frame))
            b=self.AppTest.from_file(str(root/'app.py'),default_timeout=30).run()
            self.assertNotIn('official_snapshot',b.session_state)
        self.assertEqual(before,(root/'data/official.csv').read_bytes())
