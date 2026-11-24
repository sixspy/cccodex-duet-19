import os
from pathlib import Path

_tmp = Path(__file__).resolve().parent / "_tmp"
_tmp.mkdir(exist_ok=True)
os.environ["数据目录"] = str(_tmp)
os.environ["夹具目录"] = str(Path(__file__).resolve().parents[2] / "fixtures")

import pytest

from app import seed
from app.services import 左装载, 右装载, 对齐, 目录
from app.modules import 对拍结论三联贯验 as 贯验


def setup_function():
    db = _tmp / "对拍.db"
    if db.exists():
        db.unlink()
    seed.初始化库()


def 灌(左事件, 右事件):
    左装载.装一批({"事件": 左事件})
    右装载.装一批({"事件": 右事件})
    对齐.跑对齐()


def test_纯对齐不撕裂():
    灌(
        [{"事件编号": "a1", "业务键": "K1", "金额分": 100, "源键": "渠甲", "事件时": "2026-11-23T10:00:00Z"}],
        [{"事件编号": "b1", "业务键": "K1", "金额分": 100, "源键": "核乙", "事件时": "2026-11-23T10:00:00Z"}],
    )
    for 式 in ("三联", "双联附件"):
        r = 贯验.跑贯验(式)
        assert r["形态"] == 式
        assert (r["差数"], r["悬数"], r["旁路账册数"]) == (0, 0, 0)
        assert r["撕裂标记"] is False
        assert r["valid"] is True
        assert r["快照编号"] == 0
    g = 贯验.读贯验()
    assert g["撕裂标记"] is False
    assert g["valid"] is True
    assert g["同票"] is True


def test_有旁路无悬_三联撕裂_双联不撕裂有快照附件():
    灌(
        [{"事件编号": "a1", "业务键": "K1", "金额分": 100, "源键": "渠甲", "事件时": "2026-11-23T10:00:00Z"}],
        [{"事件编号": "b1", "业务键": "K1", "金额分": 150, "源键": "核乙", "事件时": "2026-11-23T10:00:00Z"}],
    )
    差行 = [r for r in 目录.差列表() if r["差型"] == "金额不符"]
    assert len(差行) == 1
    升 = 贯验.升格旁路(编号=差行[0]["编号"])
    assert 升["旁路账册数"] == 1
    assert 升["差数"] == 0
    assert 升["悬数"] == 0

    三 = 贯验.跑贯验("三联")
    assert 三["撕裂标记"] is True
    assert 三["valid"] is False
    assert 三["快照编号"] == 0

    双 = 贯验.跑贯验("双联附件")
    assert 双["撕裂标记"] is False
    assert 双["valid"] is True
    assert 双["旁路账册数"] == 1
    assert 双["快照编号"] > 0
    快照 = 贯验.快照读取(双["快照编号"])
    assert 快照["结论编号"] == 双["编号"]
    assert 快照["旁路账册数"] == 1
    assert 快照["快照"][0]["业务键"] == "K1"

    # 有旁路无悬时两形态判撕裂须可区分
    assert 贯验.判撕裂("三联", 0, 0, 1) != 贯验.判撕裂("双联附件", 0, 0, 1)


def test_有悬两边均撕裂():
    灌(
        [{"事件编号": "a1", "业务键": "K2", "金额分": 200, "源键": "渠甲", "事件时": "2026-11-23T10:00:00Z"}],
        [],
    )
    for 式 in ("三联", "双联附件"):
        r = 贯验.跑贯验(式)
        assert r["悬数"] == 1
        assert r["撕裂标记"] is True
        assert r["valid"] is False


def test_并发跑结论不双成功():
    灌(
        [{"事件编号": "a1", "业务键": "K1", "金额分": 100, "源键": "渠甲", "事件时": "2026-11-23T10:00:00Z"}],
        [{"事件编号": "b1", "业务键": "K1", "金额分": 100, "源键": "核乙", "事件时": "2026-11-23T10:00:00Z"}],
    )
    from concurrent.futures import ThreadPoolExecutor

    def 试跑(_):
        try:
            贯验.跑贯验()
            return "成"
        except 贯验.并发冲突:
            return "冲突"

    with ThreadPoolExecutor(max_workers=8) as 池:
        结果 = list(池.map(试跑, range(8)))
    assert 结果.count("成") == 1
    assert 结果.count("冲突") == 7
    assert len(贯验.贯验结论列表()) == 1


def test_升格并发计数不漂():
    灌(
        [
            {"事件编号": "a1", "业务键": "K1", "金额分": 100, "源键": "渠甲", "事件时": "2026-11-23T10:00:00Z"},
            {"事件编号": "a2", "业务键": "K2", "金额分": 200, "源键": "渠甲", "事件时": "2026-11-23T10:00:01Z"},
        ],
        [
            {"事件编号": "b1", "业务键": "K1", "金额分": 150, "源键": "核乙", "事件时": "2026-11-23T10:00:00Z"},
            {"事件编号": "b2", "业务键": "K2", "金额分": 260, "源键": "核乙", "事件时": "2026-11-23T10:00:01Z"},
        ],
    )
    from concurrent.futures import ThreadPoolExecutor

    差行 = [r for r in 目录.差列表() if r["差型"] == "金额不符"]
    assert len(差行) == 2

    def 升(编号):
        贯验.升格旁路(编号=编号)
        return True

    def 跑(_):
        try:
            return 贯验.跑贯验("三联")
        except 贯验.并发冲突:
            return None

    with ThreadPoolExecutor(max_workers=6) as 池:
        f1 = [池.submit(升, r["编号"]) for r in 差行]
        f2 = [池.submit(跑, i) for i in range(4)]
        [f.result() for f in f1]
        跑果 = [f.result() for f in f2]

    终 = 贯验.读贯验()
    assert (终["差数"], 终["悬数"], 终["旁路账册数"]) == (0, 0, 2)
    for r in 跑果:
        if r is not None:
            # 成功的跑：落库三计数必与当时三表一致（同事务），且集合自洽
            assert r["差数"] + r["旁路账册数"] == 2
            assert r["悬数"] == 0
    # 升格后未重跑：最新结论与三表不同票，valid 须能看出来
    assert 终["同票"] is False
    assert 终["valid"] is False
    贯验.跑贯验("三联")
    再 = 贯验.读贯验()
    assert 再["同票"] is True
    assert 再["旁路账册数"] == 2


def test_只读接口字段与只读性():
    灌([], [])
    前 = len(贯验.贯验结论列表())
    g = 贯验.读贯验()
    for k in ("差数", "悬数", "旁路账册数", "撕裂标记", "valid"):
        assert k in g
    assert len(贯验.贯验结论列表()) == 前  # 只读不落库


def test_形态择定与轨规默认():
    assert 贯验.当前形态() == "三联"
    目录.改轨规({"贯验形态": "双联附件"})
    assert 贯验.当前形态() == "双联附件"
    assert 贯验.规范形态("双联加附件") == "双联附件"
    assert 贯验.规范形态("别的") == "三联"
    r = 贯验.跑贯验()  # 未指定 → 读轨规
    assert r["形态"] == "双联附件"


def test_升格无目标_404语义无残行():
    灌([], [])
    with pytest.raises(贯验.无升格目标):
        贯验.升格旁路(业务键="不存在")
    assert 贯验.旁路列表() == []
