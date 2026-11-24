"""金额容差策略落桩测试：闭区间边界、改容差重算、并发互斥。"""
import os
import threading
from pathlib import Path

_tmp = Path(__file__).resolve().parent / "_tmp"
_tmp.mkdir(exist_ok=True)
os.environ["数据目录"] = str(_tmp)
os.environ["夹具目录"] = str(Path(__file__).resolve().parents[2] / "fixtures")

from fastapi.testclient import TestClient

from app import seed
from app.main import app
from app.modules.金额容差策略 import 裁决, 形态
from app.services import 左装载, 右装载, 对齐, 结论, 目录


def setup_function():
    db = _tmp / "对拍.db"
    if db.exists():
        db.unlink()
    seed.初始化库()


def _装双边(左事件, 右事件):
    左装载.装一批({"事件": 左事件})
    右装载.装一批({"事件": 右事件})


def _差索引() -> dict:
    return {r["业务键"]: r for r in 目录.差列表()}


# ---------- 纯策略：三种夹具 ----------

def test_差小于容差判对齐无凭证():
    v = 裁决("K", 1000, 990, 20)
    assert v["差型"] == "对齐"
    assert v["valid"] is True
    assert v["贴边"] is False
    assert v["差额分"] == 10
    assert v["旁路凭证"] is None


def test_差恰等于容差闭区间对齐无凭证():
    v = 裁决("K", 1000, 980, 20)
    assert v["差型"] == "对齐"          # 闭区间：等值也对齐
    assert v["valid"] is True
    assert v["贴边"] is True           # 与纯内对齐可区分
    assert v["旁路凭证"] is None       # 无旁路凭证
    assert v["形态"] == "闭区间"


def test_差大于容差不符():
    v = 裁决("K", 1000, 970, 20)
    assert v["差型"] == "金额不符"
    assert v["valid"] is False
    assert v["贴边"] is False
    assert v["差额分"] == 30
    assert v["旁路凭证"] is None


def test_零容差等值对齐():
    # 默认 happy path：容差 0，等值必须对齐
    assert 裁决("K", 500, 500, 0)["valid"] is True
    assert 裁决("K", 500, 499, 0)["valid"] is False


# ---------- 端到端：跑对齐的边界落点 ----------

def test_跑对齐三档边界与悬账隔离():
    _装双边(
        [
            {"事件编号": "l1", "业务键": "内", "金额分": 1000, "源键": "渠甲", "事件时": "2026-11-24T10:00:00Z"},
            {"事件编号": "l2", "业务键": "边", "金额分": 1000, "源键": "渠甲", "事件时": "2026-11-24T10:00:01Z"},
            {"事件编号": "l3", "业务键": "超", "金额分": 1000, "源键": "渠甲", "事件时": "2026-11-24T10:00:02Z"},
        ],
        [
            {"事件编号": "r1", "业务键": "内", "金额分": 990, "源键": "核乙", "事件时": "2026-11-24T10:00:00Z"},
            {"事件编号": "r2", "业务键": "边", "金额分": 980, "源键": "核乙", "事件时": "2026-11-24T10:00:01Z"},
            {"事件编号": "r3", "业务键": "超", "金额分": 970, "源键": "核乙", "事件时": "2026-11-24T10:00:02Z"},
        ],
    )
    目录.改轨规({"金额容差分": "20"})
    r = 对齐.跑对齐()
    assert r["策略形态"] == "闭区间"
    assert r["贴边对齐"] == 1
    行 = _差索引()
    assert 行["内"]["差型"] == "对齐"
    assert 行["边"]["差型"] == "对齐"
    assert "贴容差边界" in 行["边"]["说明"]
    assert 行["超"]["差型"] == "金额不符"

    # 对齐键（含贴边）不进悬账；不符键本形态也不落悬账，悬账只属于缺边
    悬键 = {h["业务键"] for h in 目录.悬列表()}
    assert {"内", "边"}.isdisjoint(悬键)
    assert 结论.跑一次()["是否通过"] is True


def test_改容差旧差作废重算无新旧并存():
    _装双边(
        [{"事件编号": "l1", "业务键": "K", "金额分": 1000, "源键": "渠甲", "事件时": "2026-11-24T10:00:00Z"}],
        [{"事件编号": "r1", "业务键": "K", "金额分": 980, "源键": "核乙", "事件时": "2026-11-24T10:00:00Z"}],
    )
    目录.改轨规({"金额容差分": "10"})
    r1 = 对齐.跑对齐()
    assert r1["对齐"] == 0  # 差20 > 10，不符
    assert _差索引()["K"]["差型"] == "金额不符"
    旧编号 = _差索引()["K"]["编号"]

    # 容差放宽到 20：旧差必须在同事务作废，不留两套
    回执 = 目录.改轨规({"金额容差分": "20"})
    assert 回执["容差变更"] is True
    assert 回执["作废对齐差行"] == 1
    assert 目录.差列表() == []
    assert 目录.悬列表() == []

    r2 = 对齐.跑对齐()
    assert r2["对齐"] == 1
    assert r2["贴边对齐"] == 1
    行 = _差索引()["K"]
    assert 行["差型"] == "对齐"
    assert 行["编号"] > 旧编号  # 全是新算的行，旧行已物理删除无残留

    # 容差没变不动作废
    回执2 = 目录.改轨规({"金额容差分": "20"})
    assert 回执2["容差变更"] is False
    assert 回执2["作废对齐差行"] == 0
    assert len(目录.差列表()) == 1


def test_改容差拒绝负数与非整数():
    import pytest
    for 坏 in ("-1", "abc"):
        with pytest.raises(ValueError):
            目录.改轨规({"金额容差分": 坏})


# ---------- 并发：跑对齐 × 跑对齐 / 改容差 × 跑对齐 ----------

def _并发装样例():
    _装双边(
        [
            {"事件编号": "l1", "业务键": "K1", "金额分": 1000, "源键": "渠甲", "事件时": "2026-11-24T10:00:00Z"},
            {"事件编号": "l2", "业务键": "K2", "金额分": 2000, "源键": "渠甲", "事件时": "2026-11-24T10:00:01Z"},
        ],
        [
            {"事件编号": "r1", "业务键": "K1", "金额分": 990, "源键": "核乙", "事件时": "2026-11-24T10:00:00Z"},
            {"事件编号": "r2", "业务键": "K2", "金额分": 1900, "源键": "核乙", "事件时": "2026-11-24T10:00:01Z"},
        ],
    )


def test_两个跑对齐并发不双成功且无重复键():
    _并发装样例()
    目录.改轨规({"金额容差分": "20"})
    错: list[Exception] = []

    def 工():
        try:
            对齐.跑对齐()
        except Exception as e:  # noqa: BLE001
            错.append(e)

    ts = [threading.Thread(target=工) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert 错 == []
    差 = 目录.差列表()
    键 = [r["业务键"] for r in 差]
    assert sorted(键) == ["K1", "K2"]          # 无重复、无新旧两套
    assert len(差) == 2


def test_改容差与跑对齐并发不得新旧两套并存():
    _并发装样例()
    目录.改轨规({"金额容差分": "5"})
    屏障 = threading.Barrier(6)
    错: list[Exception] = []

    def 跑():
        try:
            屏障.wait()
            对齐.跑对齐()
        except Exception as e:  # noqa: BLE001
            错.append(e)

    def 改():
        try:
            屏障.wait()
            目录.改轨规({"金额容差分": "20"})
        except Exception as e:  # noqa: BLE001
            错.append(e)

    ts = [threading.Thread(target=跑) for _ in range(5)] + [threading.Thread(target=改)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert 错 == []

    # 终态只能自洽于一种容差口径：要么差被作废待重跑（0 行），
    # 要么全部行的时刻一致且结论按当前容差成立——绝不允许混合
    差 = 目录.差列表()
    if 差:
        时刻集 = {r["时刻"] for r in 差}
        assert len(时刻集) == 1
        键 = [r["业务键"] for r in 差]
        assert len(键) == len(set(键))
        assert 结论.跑一次()["是否通过"] is True
    当前容差 = int(目录.轨规()["金额容差分"])
    assert 当前容差 == 20


# ---------- HTTP：只读裁决接口 ----------

def test_只读裁决接口():
    client = TestClient(app)
    r = client.get(
        "/api/容差裁决",
        params={"业务键": "ORD-X", "左金额分": 1000, "右金额分": 980, "容差分": 20},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["业务键"] == "ORD-X"
    assert body["差型"] == "对齐"
    assert body["贴边"] is True
    assert body["valid"] is True
    assert body["旁路凭证"] is None
    assert body["容差分"] == 20

    # 缺省容差分 → 读轨规
    目录.改轨规({"金额容差分": "10"})
    r2 = client.get(
        "/api/容差裁决",
        params={"业务键": "ORD-X", "左金额分": 1000, "右金额分": 980},
    )
    assert r2.json()["valid"] is False

    # 轨规坏值返回 400，不 500
    r3 = client.post("/api/轨规", json={"金额容差分": "坏值"})
    assert r3.status_code == 400
    assert int(目录.轨规()["金额容差分"]) == 10  # 坏值没落库
