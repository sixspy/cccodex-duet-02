from app.db import 连接
from app.services.写闸 import 写闸

def 轨规() -> dict:
    conn = 连接()
    rows = conn.execute("SELECT 键, 值 FROM 轨规").fetchall()
    conn.close()
    return {r["键"]: r["值"] for r in rows}

def 改轨规(体: dict) -> dict:
    """写轨规。金额容差分变更时，同事务作废旧对齐差/悬账。

    与跑对齐共用写闸：二者互斥，不会互相覆盖；作废与写规同成败，
    不留「新容差 + 旧差」的两套结果（重跑对齐即按新容差重算）。
    """
    新容差 = 体.get("金额容差分")
    if 新容差 is not None:
        try:
            新容差 = int(新容差)
        except (TypeError, ValueError):
            raise ValueError("金额容差分须为整数分")
        if 新容差 < 0:
            raise ValueError("金额容差分不可为负")
        体 = {**体, "金额容差分": str(新容差)}

    with 写闸() as conn:
        旧行 = conn.execute(
            "SELECT 值 FROM 轨规 WHERE 键='金额容差分'"
        ).fetchone()
        旧容差 = int(旧行["值"]) if 旧行 else 0

        for k, v in 体.items():
            conn.execute(
                "INSERT INTO 轨规(键, 值) VALUES (?, ?) ON CONFLICT(键) DO UPDATE SET 值=excluded.值",
                (k, str(v)),
            )

        容差变更 = 新容差 is not None and 新容差 != 旧容差
        作废差行 = 0
        作废悬行 = 0
        if 容差变更:
            作废差行 = conn.execute("SELECT COUNT(*) AS c FROM 对齐差").fetchone()["c"]
            作废悬行 = conn.execute("SELECT COUNT(*) AS c FROM 悬账单").fetchone()["c"]
            conn.execute("DELETE FROM 对齐差")
            conn.execute("DELETE FROM 悬账单")

    out = 轨规()
    out["容差变更"] = 容差变更
    out["作废对齐差行"] = 作废差行
    out["作废悬账行"] = 作废悬行
    return out

def 源列表() -> list[dict]:
    conn = 连接()
    rows = conn.execute("SELECT * FROM 源登记 ORDER BY 轨别, 源键").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def 左列表(限制: int = 300) -> list[dict]:
    conn = 连接()
    rows = conn.execute("SELECT * FROM 左轨流水 ORDER BY 处理时 DESC LIMIT ?", (限制,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def 右列表(限制: int = 300) -> list[dict]:
    conn = 连接()
    rows = conn.execute("SELECT * FROM 右轨流水 ORDER BY 处理时 DESC LIMIT ?", (限制,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def 差列表() -> list[dict]:
    conn = 连接()
    rows = conn.execute("SELECT * FROM 对齐差 ORDER BY 编号 DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def 悬列表() -> list[dict]:
    conn = 连接()
    rows = conn.execute("SELECT * FROM 悬账单 ORDER BY 编号 DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def 结论列表() -> list[dict]:
    conn = 连接()
    rows = conn.execute("SELECT * FROM 对拍结论 ORDER BY 编号 DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def 概览() -> dict:
    conn = 连接()
    g = 轨规()
    out = {
        "站名": g.get("站名", "对拍"),
        "骨架": g.get("骨架", ""),
        "皮": g.get("皮", ""),
        "去皮": g.get("去皮", ""),
        "左笔数": conn.execute("SELECT COUNT(*) AS c FROM 左轨流水").fetchone()["c"],
        "右笔数": conn.execute("SELECT COUNT(*) AS c FROM 右轨流水").fetchone()["c"],
        "对齐差数": conn.execute("SELECT COUNT(*) AS c FROM 对齐差").fetchone()["c"],
        "悬账数": conn.execute("SELECT COUNT(*) AS c FROM 悬账单").fetchone()["c"],
        "结论数": conn.execute("SELECT COUNT(*) AS c FROM 对拍结论").fetchone()["c"],
    }
    conn.close()
    return out
