"""同业务键对齐：双边金额比对，落对齐差 + 悬账单。

并发正确性（写闸保证，见 app.services.写闸）：
- 整段在一个 BEGIN IMMEDIATE 事务内：读轨规、清旧差、写新差、写悬账同成败；
- 两个跑对齐并发不会双成功，第二个等锁后看到的已是首批的结果；
- 改容差（目录.改轨规）走同一把写闸，与跑对齐互斥，互不覆盖；
- 清旧差与写新差同事务，任何失败整体回滚，绝不允许新旧两套差并存。
"""
from __future__ import annotations

from app.modules.金额容差策略 import 裁决, 形态
from app.seed import 此刻
from app.services.写闸 import 写闸


def 跑对齐() -> dict:
    时刻 = 此刻()
    with 写闸() as conn:
        # 轨规在写事务内读：本次裁决用的容差与本事务看到的库状态一致
        规行 = conn.execute(
            "SELECT 值 FROM 轨规 WHERE 键='金额容差分'"
        ).fetchone()
        容差 = int(规行["值"]) if 规行 else 0

        # 清空上次对齐结果（与下面的写入同事务，失败一起回滚）
        conn.execute("DELETE FROM 对齐差")
        conn.execute("DELETE FROM 悬账单")

        左汇总: dict[str, int] = {}
        左代表: dict[str, str] = {}
        for r in conn.execute(
            "SELECT * FROM 左轨流水 WHERE 命运='已入左'"
        ).fetchall():
            k = r["业务键"]
            左汇总[k] = 左汇总.get(k, 0) + int(r["金额分"])
            左代表[k] = r["事件编号"]

        右汇总: dict[str, int] = {}
        右代表: dict[str, str] = {}
        for r in conn.execute(
            "SELECT * FROM 右轨流水 WHERE 命运='已入右'"
        ).fetchall():
            k = r["业务键"]
            右汇总[k] = 右汇总.get(k, 0) + int(r["金额分"])
            右代表[k] = r["事件编号"]

        所有键 = set(左汇总) | set(右汇总)
        对齐 = 0
        贴边数 = 0
        差 = 0
        悬 = 0

        for k in sorted(所有键):
            有左 = k in 左汇总
            有右 = k in 右汇总
            if 有左 and 有右:
                la, ra = 左汇总[k], 右汇总[k]
                v = 裁决(k, la, ra, 容差)
                if v["valid"]:
                    说明 = (
                        f"双边金额贴容差边界(|差|={v['差额分']}={容差})，闭区间判对齐"
                        if v["贴边"]
                        else f"双边金额在容差内(|差|={v['差额分']}≤{容差})"
                    )
                    conn.execute(
                        "INSERT INTO 对齐差(业务键,左金额分,右金额分,差型,说明,时刻) VALUES (?,?,?,?,?,?)",
                        (k, la, ra, "对齐", 说明, 时刻),
                    )
                    对齐 += 1
                    if v["贴边"]:
                        贴边数 += 1
                else:
                    conn.execute(
                        "INSERT INTO 对齐差(业务键,左金额分,右金额分,差型,说明,时刻) VALUES (?,?,?,?,?,?)",
                        (
                            k,
                            la,
                            ra,
                            "金额不符",
                            f"|差|={v['差额分']}>容差{容差}；左{la}-右{ra}",
                            时刻,
                        ),
                    )
                    差 += 1
            elif 有左:
                conn.execute(
                    "INSERT INTO 对齐差(业务键,左金额分,右金额分,差型,说明,时刻) VALUES (?,?,?,?,?,?)",
                    (k, 左汇总[k], None, "右缺", "仅左轨有键", 时刻),
                )
                conn.execute(
                    "INSERT INTO 悬账单(业务键,悬边,金额分,事件编号,原因,时刻) VALUES (?,?,?,?,?,?)",
                    (k, "左", 左汇总[k], 左代表.get(k, ""), "右轨缺键", 时刻),
                )
                悬 += 1
                差 += 1
            else:
                conn.execute(
                    "INSERT INTO 对齐差(业务键,左金额分,右金额分,差型,说明,时刻) VALUES (?,?,?,?,?,?)",
                    (k, None, 右汇总[k], "左缺", "仅右轨有键", 时刻),
                )
                conn.execute(
                    "INSERT INTO 悬账单(业务键,悬边,金额分,事件编号,原因,时刻) VALUES (?,?,?,?,?,?)",
                    (k, "右", 右汇总[k], 右代表.get(k, ""), "左轨缺键", 时刻),
                )
                悬 += 1
                差 += 1

        return {
            "键总数": len(所有键),
            "对齐": 对齐,
            "差与悬": 差,
            "悬账": 悬,
            "贴边对齐": 贴边数,
            "容差分": 容差,
            "策略形态": 形态,
            "时刻": 时刻,
        }
