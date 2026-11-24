import os
from pathlib import Path

_tmp = Path(__file__).resolve().parent / "_tmp"
_tmp.mkdir(exist_ok=True)
os.environ["数据目录"] = str(_tmp)
os.environ["夹具目录"] = str(Path(__file__).resolve().parents[2] / "fixtures")

from fastapi.testclient import TestClient

from app.main import app


def 客户端():
    db = _tmp / "对拍.db"
    if db.exists():
        db.unlink()
    return TestClient(app)


def test_夹具路由可灌():
    with 客户端() as c:
        r = c.post("/api/左轨/夹具/左轨样例")
        assert r.status_code == 200
        assert r.json()["入流"] == 3
        r = c.post("/api/右轨/夹具/右轨样例")
        assert r.status_code == 200
        assert r.json()["入流"] == 3


def test_三联贯验只读接口字段():
    with 客户端() as c:
        r = c.get("/api/三联贯验")
        assert r.status_code == 200
        d = r.json()
        for k in ("差数", "悬数", "旁路账册数", "撕裂标记", "valid"):
            assert k in d
        # 只读：连刷两次不落贯验结论
        assert c.get("/api/贯验结论").json() == []


def test_贯验跑与快照回读与空桩():
    with 客户端() as c:
        c.post("/api/左轨/装载", json={"事件": [
            {"事件编号": "a1", "业务键": "K1", "金额分": 100, "源键": "渠甲", "事件时": "2026-11-23T10:00:00Z"}
        ]})
        c.post("/api/右轨/装载", json={"事件": [
            {"事件编号": "b1", "业务键": "K1", "金额分": 150, "源键": "核乙", "事件时": "2026-11-23T10:00:00Z"}
        ]})
        c.post("/api/对齐/跑")
        r = c.post("/api/旁路账册/升格", json={"业务键": "K1"})
        assert r.status_code == 200
        assert r.json()["旁路账册数"] == 1

        r = c.post("/api/对拍结论/贯验跑", json={"形态": "双联附件"})
        assert r.status_code == 200
        d = r.json()
        assert d["撕裂标记"] is False and d["valid"] is True and d["快照编号"] > 0

        r = c.get(f"/api/贯验快照/{d['快照编号']}")
        assert r.status_code == 200
        assert r.json()["快照"][0]["业务键"] == "K1"

        桩 = c.get("/api/空桩").json()
        assert "对拍结论三联贯验" not in 桩["空桩"]
