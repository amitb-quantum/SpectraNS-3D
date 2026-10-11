import json
import sys
import pytest
from launch_h100_smoke import main


def test_cloud_launcher_defaults_to_plan_only(tmp_path,monkeypatch,capsys):
    out=tmp_path/'never_created'
    monkeypatch.setattr(sys,'argv',['launch_h100_smoke.py','--output',str(out)])
    assert main()==0
    plan=json.loads(capsys.readouterr().out)
    assert plan['mode']=='PLAN ONLY' and len(plan['commands'])==8
    assert not out.exists()


def test_cloud_execution_requires_approval_record(monkeypatch):
    monkeypatch.setattr(sys,'argv',['launch_h100_smoke.py','--execute'])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code==2
