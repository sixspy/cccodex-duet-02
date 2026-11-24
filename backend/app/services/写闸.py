"""写闸：改容差与跑对齐共用的库级互斥。

SQLite 单写者模型下，BEGIN IMMEDIATE 一进事务即拿写锁（RESERVED），
第二个写者阻塞到 busy timeout 后报 SQLITE_BUSY，不会双成功。
进程内再叠一把 threading.Lock，省掉无谓的 BUSY 重试与等待。
"""
from __future__ import annotations

import sqlite3
import threading

from app.db import 连接

_进程锁 = threading.RLock()


class 写闸:
    """进入即拿进程锁 + BEGIN IMMEDIATE；退出提交/回滚并释放。

    读轨规、清旧差、写新差必须全部落在同一事务里，同成败。
    """

    def __init__(self, timeout: float = 10.0):
        self._timeout = timeout
        self._conn: sqlite3.Connection | None = None
        self._拿到进程锁 = False

    def __enter__(self) -> sqlite3.Connection:
        _进程锁.acquire()
        self._拿到进程锁 = True
        try:
            conn = 连接()
            conn.execute(f"PRAGMA busy_timeout = {int(self._timeout * 1000)}")
            conn.execute("BEGIN IMMEDIATE")
            self._conn = conn
            return conn
        except Exception:
            if self._conn is not None:
                self._conn.close()
            _进程锁.release()
            self._拿到进程锁 = False
            raise

    def __exit__(self, exc_type, exc, tb) -> None:
        conn = self._conn
        try:
            if exc_type is None:
                conn.commit()
            else:
                conn.rollback()
        finally:
            conn.close()
            if self._拿到进程锁:
                _进程锁.release()
