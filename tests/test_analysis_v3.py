import csv
import pytest
from analyze_runs_v3 import read_rows


@pytest.mark.parametrize('bad_key,bad_value',[('E','nan'),('tail_ratio','inf'),('wmax',''),('t','-1')])
def test_bad_historical_values_cannot_pass_screen(tmp_path,bad_key,bad_value):
    keys=['t','E','Z','eps','wmax','bkm','tail_ratio','div_max']
    rows=[dict(zip(keys,['0','1','1','.1','1','0','0','0'])),dict(zip(keys,['1','.9','1','.1','1','1','0','0']))]
    rows[1][bad_key]=bad_value
    p=tmp_path/'run.csv'
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys)
        w.writeheader();w.writerows(rows)
    with pytest.raises(ValueError):
        read_rows(p)
