"""Read-only official refresh for a multi-user deployment."""
import io
import json
import tempfile
import zipfile
from pathlib import Path
import pandas as pd
from fetch_official import fetch
from lottery import COLUMNS, validate

ROOT = Path(__file__).resolve().parent

def check_update(previous, current):
    """Never accept a snapshot that removes or changes published draw records."""
    before = previous.set_index('issue')
    after = current.set_index('issue')
    if not before.index.isin(after.index).all():
        raise ValueError('官方响应缺少已有期号，保留原数据，请稍后重试')
    cols = [c for c in COLUMNS if c not in ('issue','source')]
    if not before[cols].equals(after.loc[before.index,cols]):
        raise ValueError('官方响应与已有记录冲突，保留原数据，需人工核查')

def official_snapshot():
    # Temporary files never replace the bundled database or another visitor's upload.
    with tempfile.TemporaryDirectory(prefix='ssq_') as folder:
        output=Path(folder)/'official.csv'
        fetch(output)
        frame,_=validate(pd.read_csv(output,dtype={'issue':str,'date':str},encoding='utf-8-sig'))
        bundled=ROOT/'data/official.csv'
        if bundled.exists():
            before,_=validate(pd.read_csv(bundled,dtype={'issue':str,'date':str},encoding='utf-8-sig'))
            check_update(before,frame)
        manifest=json.loads(output.with_suffix('.provenance.json').read_text(encoding='utf-8'))
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            z.write(output,'official.csv')
            for item in manifest['raw']:
                path=Path(item['file'])
                name='raw/'+path.name
                z.write(path,name)
                item['file']=name
            z.writestr('official.provenance.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        return frame,manifest,archive.getvalue()
