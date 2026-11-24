from fastapi import APIRouter, HTTPException
from app.modules.金额容差策略 import 只读接口 as 容差裁决
from app.services import 目录, 左装载, 右装载, 对齐, 结论, 夹具, 统计, 说明

路由 = APIRouter()

@路由.get("/api/概览")
def api_概览():
    return 目录.概览()

@路由.get("/api/轨规")
def api_轨规():
    return 目录.轨规()

@路由.post("/api/轨规")
def api_改轨规(体: dict):
    try:
        return 目录.改轨规(体)
    except ValueError as e:
        raise HTTPException(400, str(e))

@路由.get("/api/容差裁决")
def api_容差裁决(业务键: str, 左金额分: int, 右金额分: int, 容差分: int | None = None):
    """只读接口：给双边金额与容差分，返差型/贴边/valid/旁路凭证，不写库。"""
    try:
        return 容差裁决(业务键, 左金额分, 右金额分, 容差分)
    except ValueError as e:
        raise HTTPException(400, str(e))

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
            if p.is_dir() and p.name != "__pycache__" and (p / "__init__.py").is_file():
                out.append(p.name)
    return {"空桩": out, "条数": len(out)}

