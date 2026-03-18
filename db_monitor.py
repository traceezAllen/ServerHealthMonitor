"""
DB Server 監控腳本

檢查各產品資料庫的 Tracker 表是否可連線、有資料：
  - iCar 570:  TK_MSP570.Tracker
  - YJGPS 540: YJ_TK2012.Tracker
  - iPet 340:  TK_MSP340.Tracker

判定標準：
  - 連線成功 + SELECT COUNT(*) FROM Tracker 回傳 > 0 = OK
  - 連線失敗或查無資料 = FAIL
  - 兩次都失敗才發 Google Chat 告警

用法：
  python db_monitor.py                   # 監控所有 DB（每 5 分鐘）
  python db_monitor.py --once            # 只執行一次
  python db_monitor.py --once icar       # 只檢查 iCar DB
"""

import sys
import time
import pymssql
from datetime import datetime

from config import (
    DbCommonConfig, ICarDbConfig, YJGPSDbConfig, IPetDbConfig,
)
from db import write_heartbeat_log
from alert import send_google_chat_alert
from logger_setup import setup_logger

logger = setup_logger("db_monitor")


# =============================================
# DB 檢查目標定義
# =============================================

DB_TARGETS = {
    "icar": {
        "label": "iCar 570 DB (TK_MSP570)",
        "config": ICarDbConfig,
    },
    "yjgps": {
        "label": "YJGPS 540 DB (YJ_TK2012)",
        "config": YJGPSDbConfig,
    },
    "ipet": {
        "label": "iPet 340 DB (TK_MSP340)",
        "config": IPetDbConfig,
    },
}


# =============================================
# 核心檢查邏輯
# =============================================

def run_db_check(cfg) -> dict:
    """
    連線到指定 DB，SELECT COUNT(*) FROM Tracker
    回傳 {"status": "OK"/"FAIL", "response_time_ms": int, "error": str|None, "tracker_count": int}
    """
    result = {"status": "FAIL", "response_time_ms": 0, "error": None, "tracker_count": 0}

    start = time.time()
    try:
        conn = pymssql.connect(
            server=cfg.HOST,
            user=cfg.USER,
            password=cfg.PASSWORD,
            database=cfg.NAME,
            timeout=DbCommonConfig.TIMEOUT_S,
            login_timeout=DbCommonConfig.TIMEOUT_S,
        )
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Tracker")
        row = cursor.fetchone()
        conn.close()

        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed

        if row and row[0] > 0:
            result["tracker_count"] = row[0]
            result["status"] = "OK"
        else:
            result["error"] = f"Tracker 表無資料 (count={row[0] if row else 'NULL'})"

    except pymssql.OperationalError as e:
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed
        result["error"] = f"連線失敗: {str(e)}"
    except pymssql.DatabaseError as e:
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed
        result["error"] = f"查詢失敗: {str(e)}"
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed
        result["error"] = f"{type(e).__name__}: {str(e)}"

    return result


def run_db_check_with_retry(cfg) -> dict:
    """執行 DB 檢查，失敗時重試一次"""
    result = run_db_check(cfg)
    if result["status"] == "OK":
        return result

    logger.warning(f"  第一次檢查失敗，3 秒後重試...")
    time.sleep(3)

    logger.info(f"  === 重試第二次 ===")
    result = run_db_check(cfg)
    if result["status"] == "FAIL":
        logger.error(f"  兩次檢查都失敗！")

    return result


def check_single_db(key: str, target: dict):
    """檢查單一 DB 並寫入 DB + 告警"""
    label = target["label"]
    cfg = target["config"]
    service_name = cfg.SERVICE_NAME

    logger.info(f"[{label}] 開始檢查 ({cfg.HOST}/{cfg.NAME})...")

    result = run_db_check_with_retry(cfg)

    if result["status"] == "OK":
        logger.info(
            f"[{label}] OK | {result['response_time_ms']}ms | "
            f"Tracker count: {result['tracker_count']}"
        )
    else:
        logger.error(
            f"[{label}] FAIL | {result['response_time_ms']}ms | {result['error']}"
        )

    # 寫入 Monitor DB
    try:
        write_heartbeat_log(
            service_name=service_name,
            status=result["status"],
            response_time_ms=result["response_time_ms"],
            error_message=result["error"],
        )
    except Exception as e:
        logger.error(f"[{label}] Monitor DB 寫入失敗: {e}")

    # 兩次重試都失敗 → 發 Google Chat 告警
    if result["status"] == "FAIL":
        logger.critical(f"[{label}] 兩次檢查都失敗！發送 Google Chat 告警...")
        send_google_chat_alert(
            service_name=f"{label} ({service_name})",
            error_message=result["error"],
            response_time_ms=result["response_time_ms"],
        )


# =============================================
# 主程式
# =============================================

def main():
    interval = DbCommonConfig.CHECK_INTERVAL_S

    # 解析目標參數
    only_target = None
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        if idx + 1 < len(sys.argv):
            only_target = sys.argv[idx + 1].lower()
    else:
        for arg in sys.argv[1:]:
            if arg.lower() in DB_TARGETS:
                only_target = arg.lower()
                break

    if only_target and only_target not in DB_TARGETS:
        logger.error(f"未知的目標: {only_target}，可用: {list(DB_TARGETS.keys())}")
        sys.exit(1)

    targets = [only_target] if only_target else list(DB_TARGETS.keys())

    logger.info("=" * 50)
    logger.info("  DB Server Monitor 啟動")
    logger.info(f"  監控目標: {', '.join(targets)}")
    logger.info(f"  檢查間隔: {interval} 秒")
    logger.info("=" * 50)

    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"\n[{now}] ===== 開始檢查 =====")

        for key in targets:
            target = DB_TARGETS[key]
            try:
                check_single_db(key, target)
            except Exception as e:
                logger.error(f"檢查 {key} 時發生未預期錯誤: {e}")

        if "--once" in sys.argv:
            logger.info("\n--once 模式，執行完畢")
            break

        logger.info(f"下次檢查: {interval} 秒後...")
        time.sleep(interval)


if __name__ == "__main__":
    main()
