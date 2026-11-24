from fastapi import APIRouter, HTTPException
from app.services import 目录, 左装载, 右装载, 对齐, 结论, 夹具, 统计, 说明
from app.modules import 对拍结论三联贯验 as 贯验

路由 = APIRouter()

@路由.get("/api/概览")
def api_概览():
    return 目录.概览()

@路由.get("/api/轨规")
def api_轨规():
    return 目录.轨规()

@路由.post("/api/轨规")
def api_改轨规(体: dict):
    return 目录.改轨规(体)

@路由.get("/api/源登记")
def api_源():
    return 目录.源列表()

@路由.get("/api/左轨")
def api_左():
    return 目录.左列表()

@路由.get("/api/右轨")
def api_右():
    return 目录.右列表()

@路由.get("/api/对齐差")
def api_差():
    return 目录.差列表()

@路由.get("/api/悬账单")
def api_悬():
    return 目录.悬列表()

@路由.get("/api/对拍结论")
def api_结论列表():
    return 目录.结论列表()

@路由.get("/api/夹具")
def api_夹具():
    return 夹具.列表()

@路由.post("/api/左轨/装载")
def api_左装(体: dict):
    return 左装载.装一批(体)

@路由.post("/api/右轨/装载")
def api_右装(体: dict):
    return 右装载.装一批(体)

@路由.post("/api/左轨/夹具/{name}")
def api_左夹(name: str):
    try:
        return 左装载.装一批(夹具.读取(name))
    except FileNotFoundError:
        raise HTTPException(404, name)

@路由.post("/api/右轨/夹具/{name}")
def api_右夹(name: str):
    try:
        return 右装载.装一批(夹具.读取(name))
    except FileNotFoundError:
        raise HTTPException(404, name)

@路由.post("/api/对齐/跑")
def api_对齐():
    return 对齐.跑对齐()

@路由.post("/api/对拍结论/跑")
def api_结论():
    return 结论.跑一次()


@路由.post("/api/对拍结论/贯验跑")
def api_贯验跑(体: dict | None = None):
    try:
        return 贯验.跑贯验((体 or {}).get("形态"))
    except 贯验.并发冲突 as e:
        raise HTTPException(409, str(e))


@路由.get("/api/三联贯验")
def api_三联贯验():
    return 贯验.读贯验()


@路由.get("/api/贯验结论")
def api_贯验结论():
    return 贯验.贯验结论列表()


@路由.get("/api/旁路账册")
def api_旁路账册():
    return 贯验.旁路列表()


@路由.post("/api/旁路账册/升格")
def api_旁路升格(体: dict):
    try:
        return 贯验.升格旁路(
            编号=体.get("编号"), 业务键=体.get("业务键"), 说明=体.get("说明") or ""
        )
    except 贯验.无升格目标 as e:
        raise HTTPException(404, str(e))


@路由.get("/api/贯验快照")
def api_贯验快照列表():
    return 贯验.快照列表()


@路由.get("/api/贯验快照/{sid}")
def api_贯验快照(sid: int):
    d = 贯验.快照读取(sid)
    if d is None:
        raise HTTPException(404, f"贯验快照{sid}不存在")
    return d


@路由.get("/api/统计/左命运")
def api_左命运():
    return 统计.左命运()

@路由.get("/api/统计/右命运")
def api_右命运():
    return 统计.右命运()

@路由.get("/api/统计/差型")
def api_差型():
    return 统计.差型分布()

@路由.get("/api/统计/悬边")
def api_悬边():
    return 统计.悬边分布()


@路由.get("/api/仓情")
def api_仓情():
    return 说明.仓情()

@路由.get("/api/空桩")
def api_空桩():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "modules"
    out = []
    if root.is_dir():
        for p in sorted(root.iterdir()):
            f = p / "__init__.py"
            if p.is_dir() and p.name != "__pycache__" and f.is_file():
                try:
                    if "空桩" in f.read_text(encoding="utf-8"):
                        out.append(p.name)
                except OSError:
                    pass
    return {"空桩": out, "条数": len(out)}

