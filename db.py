"""
共用 DB 操作 — 寫入 Monitor_HeartbeatLog / 更新 Monitor_ServiceStatus
"""

import pymssql
from config import MonitorDBConfig
from logger_setup import setup_logger

logger = setup_logger("db")


def get_connection():
    return pymssql.connect(
        server=MonitorDBConfig.HOST,
        user=MonitorDBConfig.USER,
        password=MonitorDBConfig.PASSWORD,
        database=MonitorDBConfig.NAME,
    )


def write_heartbeat_log(service_name: str, status: str, response_time_ms: int, error_message: str = None):
    """寫入一筆檢查紀錄到 Monitor_HeartbeatLog + 更新 Monitor_ServiceStatus"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 先查 ServiceId
        cursor.execute("SELECT Id FROM Monitor_Service WHERE ServiceName = %s", (service_name,))
        row = cursor.fetchone()
        if not row:
            logger.warning(f"找不到服務: {service_name}，跳過寫入")
            conn.close()
            return

        service_id = row[0]

        # 寫入 HeartbeatLog
        cursor.execute(
            """
            INSERT INTO Monitor_HeartbeatLog (ServiceId, CheckTime, Status, ResponseTimeMs, ErrorMessage)
            VALUES (%s, GETDATE(), %s, %s, %s)
            """,
            (service_id, status, response_time_ms, error_message),
        )

        # 更新 ServiceStatus（UPSERT）
        cursor.execute(
            """
            MERGE Monitor_ServiceStatus AS target
            USING (SELECT %s AS ServiceId) AS source
            ON target.ServiceId = source.ServiceId
            WHEN MATCHED THEN
                UPDATE SET
                    LastCheckTime = GETDATE(),
                    LastStatus = %s,
                    ConsecutiveFailCount = CASE WHEN %s = 'FAIL' THEN ConsecutiveFailCount + 1 ELSE 0 END,
                    LastErrorMessage = %s,
                    LastResponseTimeMs = %s
            WHEN NOT MATCHED THEN
                INSERT (ServiceId, LastCheckTime, LastStatus, ConsecutiveFailCount, LastErrorMessage, LastResponseTimeMs)
                VALUES (%s, GETDATE(), %s, CASE WHEN %s = 'FAIL' THEN 1 ELSE 0 END, %s, %s);
            """,
            (
                service_id,
                status, status, error_message, response_time_ms,
                service_id, status, status, error_message, response_time_ms,
            ),
        )

        conn.commit()
        conn.close()
        logger.info(f"[DB] {service_name} → {status} ({response_time_ms}ms)")

    except Exception as e:
        logger.error(f"[DB ERROR] 寫入失敗: {e}")


def check_alert_threshold(service_name: str) -> bool:
    """檢查是否超過告警閾值，回傳 True = 需要告警"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT ss.ConsecutiveFailCount, s.FailThreshold
            FROM Monitor_ServiceStatus ss
            JOIN Monitor_Service s ON ss.ServiceId = s.Id
            WHERE s.ServiceName = %s
            """,
            (service_name,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            fail_count, threshold = row
            # 剛好等於閾值時才告警（避免重複告警）
            return fail_count == threshold

        return False

    except Exception as e:
        logger.error(f"[DB ERROR] 檢查閾值失敗: {e}")
        return False
