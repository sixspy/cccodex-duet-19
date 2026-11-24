"""对拍结论三联贯验：结论徽章与对齐差/悬账单/旁路账册三表同票。

形态二择一（轨规「贯验形态」或跑时指定）：
- 三联：差+悬+旁路账册三联互证，旁路账册行参与撕裂计数，结论读三计数集合。
- 双联附件：差+悬双联判撕裂，旁路账册不进撕裂计数，跑结论时落贯验快照表附件，可回读。

硬约束：
- 贯验锁：跑结论并发只许一个成功（不加锁会双成功）；升格与跑结论同锁，计数不漂。
- 三读写（差/悬/旁路三计数 + 结论落库 + 快照附件）同事务同成败。
- 撕裂判定真实读三表计数，不是只改文案。
"""
from __future__ import annotations

import json
import threading

from app.db import 连接
from app.seed import 此刻

NAME = "对拍结论三联贯验"

形态集 = ("三联", "双联附件")
默认形态 = "三联"

贯验锁 = threading.Lock()


class 并发冲突(Exception):
    """已有贯验跑/升格持锁，本次跑结论不得双成功。"""


class 无升格目标(Exception):
    """找不到可升格进旁路账册的对齐差行。"""


def 规范形态(值) -> str:
    v = str(值 or "").strip()
    if v in ("双联附件", "双联加附件", "双联"):
        return "双联附件"
    return "三联"


def 当前形态() -> str:
    conn = 连接()
    try:
        r = conn.execute("SELECT 值 FROM 轨规 WHERE 键='贯验形态'").fetchone()
        return 规范形态(r["值"]) if r else 默认形态
    finally:
        conn.close()


def _三计数(conn) -> tuple[int, int, int]:
    差 = conn.execute(
        "SELECT COUNT(*) AS c FROM 对齐差 WHERE 差型<>'对齐'"
    ).fetchone()["c"]
    悬 = conn.execute("SELECT COUNT(*) AS c FROM 悬账单").fetchone()["c"]
    旁 = conn.execute("SELECT COUNT(*) AS c FROM 旁路账册").fetchone()["c"]
    return 差, 悬, 旁


def 判撕裂(形态: str, 差数: int, 悬数: int, 旁路账册数: int) -> bool:
    """纯对齐不撕裂；有悬两边均撕裂；有旁路无悬：三联撕裂、双联附件不撕裂。"""
    if 规范形态(形态) == "双联附件":
        return (差数 + 悬数) > 0
    return (差数 + 悬数 + 旁路账册数) > 0


def 跑贯验(形态: str | None = None) -> dict:
    """跑三联贯验结论：三表计数与结论落库同事务，并发只许单成功。"""
    if not 贯验锁.acquire(blocking=False):
        raise 并发冲突("已有贯验跑或旁路升格在进行，拒绝双成功")
    try:
        式 = 规范形态(形态) if 形态 else 当前形态()
        conn = 连接()
        try:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            try:
                差, 悬, 旁 = _三计数(conn)
                撕裂 = 判撕裂(式, 差, 悬, 旁)
                时刻 = 此刻()
                快照编号 = 0
                # 双联附件：旁路账册不进撕裂计数，落快照表附件（可回读）
                预写快照 = None
                if 式 == "双联附件" and 旁 > 0:
                    行 = [
                        dict(r)
                        for r in conn.execute(
                            "SELECT * FROM 旁路账册 ORDER BY 编号"
                        ).fetchall()
                    ]
                    预写快照 = json.dumps(行, ensure_ascii=False)
                说明 = (
                    f"{式}贯验 差{差}/悬{悬}/旁{旁} "
                    + ("撕裂" if 撕裂 else "同票不撕裂")
                )
                cur = conn.execute(
                    """INSERT INTO 贯验结论
                       (时刻,形态,差数,悬数,旁路账册数,撕裂标记,valid,快照编号,说明)
                       VALUES (?,?,?,?,?,?,?,0,?)""",
                    (时刻, 式, 差, 悬, 旁, 1 if 撕裂 else 0, 0 if 撕裂 else 1, 说明),
                )
                结论编号 = cur.lastrowid
                if 预写快照 is not None:
                    cur = conn.execute(
                        "INSERT INTO 贯验快照(结论编号,旁路账册数,快照,时刻) VALUES (?,?,?,?)",
                        (结论编号, 旁, 预写快照, 时刻),
                    )
                    快照编号 = cur.lastrowid
                    conn.execute(
                        "UPDATE 贯验结论 SET 快照编号=? WHERE 编号=?",
                        (快照编号, 结论编号),
                    )
                    说明 += f" 旁路{旁}行进快照附件#{快照编号}"
                    conn.execute(
                        "UPDATE 贯验结论 SET 说明=? WHERE 编号=?", (说明, 结论编号)
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
        return {
            "编号": 结论编号,
            "形态": 式,
            "时刻": 时刻,
            "差数": 差,
            "悬数": 悬,
            "旁路账册数": 旁,
            "撕裂标记": 撕裂,
            "valid": not 撕裂,
            "快照编号": 快照编号,
            "说明": 说明,
        }
    finally:
        贯验锁.release()


def 读贯验() -> dict:
    """三联贯验只读接口：差数、悬数、旁路账册数、撕裂标记、valid。

    撕裂标记按当前入库三计数现算；valid=不撕裂且最新入库结论与当前三表同票。
    只读，不落库；与贯验跑/升格同锁，三计数一次读齐不漂。
    """
    式 = 当前形态()
    with 贯验锁:
        conn = 连接()
        try:
            差, 悬, 旁 = _三计数(conn)
            行 = conn.execute(
                "SELECT * FROM 贯验结论 ORDER BY 编号 DESC LIMIT 1"
            ).fetchone()
            结论 = dict(行) if 行 else None
        finally:
            conn.close()
    撕裂 = 判撕裂(式, 差, 悬, 旁)
    if 结论 is not None:
        结论["撕裂标记"] = bool(结论["撕裂标记"])
        结论["valid"] = bool(结论["valid"])
    同票 = bool(
        结论
        and 结论["差数"] == 差
        and 结论["悬数"] == 悬
        and 结论["旁路账册数"] == 旁
        and 结论["撕裂标记"] == 撕裂
    )
    return {
        "形态": 式,
        "差数": 差,
        "悬数": 悬,
        "旁路账册数": 旁,
        "撕裂标记": 撕裂,
        "同票": 同票,
        "valid": (not 撕裂) and 同票,
        "结论": 结论,
        "说明": (
            "最新结论与三表同票"
            if 同票
            else ("尚无贯验结论" if 结论 is None else "结论与三表撕裂/计数已漂，须重跑贯验")
        ),
    }


def 升格旁路(编号: int | None = None, 业务键: str | None = None, 说明: str = "") -> dict:
    """对齐差旁路升格：把一条非对齐差行移入旁路账册（与贯验跑同锁，计数不漂）。"""
    with 贯验锁:
        conn = 连接()
        try:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            try:
                行 = None
                if 编号 is not None:
                    行 = conn.execute(
                        "SELECT * FROM 对齐差 WHERE 编号=? AND 差型<>'对齐'", (编号,)
                    ).fetchone()
                if 行 is None and 业务键:
                    行 = conn.execute(
                        "SELECT * FROM 对齐差 WHERE 业务键=? AND 差型<>'对齐' ORDER BY 编号 DESC LIMIT 1",
                        (业务键,),
                    ).fetchone()
                if 行 is None:
                    raise 无升格目标(f"无可升格的对齐差行: 编号={编号} 业务键={业务键}")
                金额 = 行["左金额分"] if 行["左金额分"] is not None else 行["右金额分"]
                时刻 = 此刻()
                cur = conn.execute(
                    "INSERT INTO 旁路账册(业务键,金额分,来源差编号,说明,时刻) VALUES (?,?,?,?,?)",
                    (
                        行["业务键"],
                        int(金额 or 0),
                        行["编号"],
                        说明 or f"{行['差型']}旁路升格",
                        时刻,
                    ),
                )
                conn.execute("DELETE FROM 对齐差 WHERE 编号=?", (行["编号"],))
                conn.execute("COMMIT")
                旁编号 = cur.lastrowid
            except Exception:
                conn.execute("ROLLBACK")
                raise
            差, 悬, 旁 = _三计数(conn)
            return {
                "ok": True,
                "旁路编号": 旁编号,
                "业务键": 行["业务键"],
                "来源差编号": 行["编号"],
                "差数": 差,
                "悬数": 悬,
                "旁路账册数": 旁,
                "时刻": 时刻,
            }
        finally:
            conn.close()


def 旁路列表() -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute("SELECT * FROM 旁路账册 ORDER BY 编号 DESC").fetchall()
        ]
    finally:
        conn.close()


def 贯验结论列表() -> list[dict]:
    conn = 连接()
    try:
        out = []
        for r in conn.execute("SELECT * FROM 贯验结论 ORDER BY 编号 DESC").fetchall():
            d = dict(r)
            d["撕裂标记"] = bool(d["撕裂标记"])
            d["valid"] = bool(d["valid"])
            out.append(d)
        return out
    finally:
        conn.close()


def 快照列表() -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT 编号,结论编号,旁路账册数,时刻 FROM 贯验快照 ORDER BY 编号 DESC"
            ).fetchall()
        ]
    finally:
        conn.close()


def 快照读取(编号: int) -> dict | None:
    conn = 连接()
    try:
        r = conn.execute("SELECT * FROM 贯验快照 WHERE 编号=?", (编号,)).fetchone()
        if r is None:
            return None
        d = dict(r)
        d["快照"] = json.loads(d["快照"] or "[]")
        return d
    finally:
        conn.close()
