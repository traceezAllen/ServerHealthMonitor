"""
SINK Server TCP 監控腳本

支援三種 SINK Server：
  - iCar 570  (port 6978)
  - YJGPS 540 (port 6971)
  - iPet 340  (port 6970)

TCP 協定格式（三者相同）：
  #[CommandCode:2][MsgNum:3][IMEICode:15][LenOfMsg:3][MSG:variable]

測試流程（依據 iCar Sink 通訊協定 v1.20）：
  TCP 連線 → SA(登入) → 等 SB+RC 回應 → 送 RD(回報位置) → 等 AK 回應 → 送 SC(登出)
  失敗時重試一次，兩次都失敗才發告警到 Google Chat

用法：
  python sink_monitor.py                  # 監控所有已設定的 SINK（每 5 分鐘）
  python sink_monitor.py --once           # 只執行一次
  python sink_monitor.py --only icar      # 只監控 iCar
  python sink_monitor.py --only yjgps     # 只監控 YJGPS
  python sink_monitor.py --only ipet      # 只監控 iPet
"""

import socket
import time
import sys
from datetime import datetime, timezone, timedelta
from config import (
    SinkCommonConfig,
    ICarSinkConfig,
    YJGPSSinkConfig,
    IPetSinkConfig,
)
from db import write_heartbeat_log, check_alert_threshold
from alert import send_google_chat_alert
from logger_setup import setup_logger

logger = setup_logger("sink_monitor")

# =============================================
# 協定封包組裝
# =============================================

def build_packet(command_code: str, msg_num: int, imei: str, msg: str = "") -> bytes:
    """
    組裝 SINK TCP 封包
    格式: #[CC:2][MsgNum:3][IMEI:15][LenOfMsg:3][MSG]
    """
    packet = (
        "#"
        + command_code                      # 2 chars
        + str(msg_num).zfill(3)             # 3 chars
        + imei.ljust(15, "0")[:15]          # 15 chars（不足補 0）
        + str(len(msg)).zfill(3)            # 3 chars
        + msg
    )
    return packet.encode("ascii")

def build_sa_packet(msg_num: int, imei: str, firmware_version: str) -> bytes:
    """建立 SA（登入）封包"""
    return build_packet("SA", msg_num, imei, firmware_version)

def build_rd_packet(msg_num: int, imei: str, rd_format: str = "icar") -> bytes:
    """
    建立 RD（回報位置）封包

    時間必須使用 UTC，本地時間會導致 Server 判定 OVERLOG 而拒絕回 AK

    依據不同 SINK Server 有不同格式：
      - iCar 570:  LEN=103, 日期 DDMMYY, GPS GSA=24 chars, 封包總長 127 bytes
      - YJGPS 540: LEN=137, 日期 DDMMYY, GPS GSA=48 chars, 封包總長 161 bytes
    兩者共同點：日期 DDMMYY、時間 HHMMSS、Lat 10 chars、Lon 11 chars、均用 UTC
    """
    now = datetime.now(timezone(timedelta(hours=8)))
    time_str = now.strftime("%H%M%S")   # HHMMSS

    if rd_format == "yjgps":
        # ========== YJGPS 540 格式 (LEN=137) ==========
        # 新版 Server 預期收到 UTC 時間，若傳送本地時間將導致 OVERLOG 錯誤並被拒絕
        now = datetime.now(timezone.utc)
        time_str = now.strftime("%H%M%S")
        date_str = now.strftime("%d%m%y")

        gps_data = (
            date_str                             #  0- 5: MMDDYY (6 chars)
            + time_str                           #  6-11: HHMMSS (6 chars)
            + "2501.9154N"                       # 12-21: Latitude+N/S (10 chars)
            + "12114.2088E"                      # 22-32: Longitude+E/W (11 chars)
            + "0.063"                            # 33-37: Speed, knots (5 chars)
            + "000"                              # 38-40: Course (3 chars)
            + "00002"                            # 41-45: Distance (5 chars)
            + "A"                                # 46:    Fixed Status (A=已定位)
            + "0"                                # 47:    Reserved/SOS (1 char)
            + "0"                                # 48:    Reserved/CASE (1 char)
            + "19"                               # 49-50: GSM CSQ (2 chars)
            + "4.29"                             # 51-54: 電池電壓 (4 chars)
            + "4"                                # 55:    電源模式
            + "0"                                # 56:    靜止逾時狀態
            + "0"                                # 57:    暫存回報資料旗標 DataLog
            + "0"                                # 58:    震動/移動回報旗標
            + "000000000"                        # 59-67: Reserved (9 chars)
            + "5YFWITLSOTQYT20000000000000000000000000000000000"   # 68-115: GPS GSA (48 chars)
            + "302"                              # 116-118: GPS GSV (3 chars)
            + "1"                                # 119:   Telecom Spec (1=3G)
            + "1FAD"                             # 120-123: LAC (4 chars hex)
            + "123944B"                          # 124-130: CID (7 chars hex)
            + "466"                              # 131-133: MCC (3 chars)
            + "092"                              # 134-136: MNC (3 chars)
        )
    else:
        # ========== iCar 570 格式 (LEN=103) ==========
        # 日期格式: DDMMYY
        now_utc = datetime.now(timezone.utc)
        date_str = now_utc.strftime("%d%m%y")
        time_str = now_utc.strftime("%H%M%S")

        gps_data = (
            date_str                             #  0- 5: DDMMYY (6 chars)
            + time_str                           #  6-11: HHMMSS (6 chars)
            + "2501.9154N"                       # 12-21: Latitude+N/S (10 chars)
            + "12114.2088E"                      # 22-32: Longitude+E/W (11 chars)
            + "A"                                # 33:    定位旗標 (A=已定位)
            + "0.000"                            # 34-38: Speed (5 chars)
            + "000"                              # 39-41: Course (3 chars)
            + "00020"                            # 42-46: Distance (5 chars)
            + "19"                               # 47-48: GSM CSQ (2 chars)
            + "4.29"                             # 49-52: 電池電壓 (4 chars)
            + "4"                                # 53:    電源模式
            + "0"                                # 54:    運作情形狀態 (0:Normal)
            + "0"                                # 55:    暫存回報資料(LOG) (0:Normal)
            + "2"                                # 56:    回報原由 (2:定時回報)
            + "1"                                # 57:    Reserved 0 註 2 / ID 身份欄位 (1:汽車)
            + "5YFWITLSOTQYT20000000000"         # 58-81: GPS GSA 衛星資料 (24 chars)
            + "302"                              # 82-84: GPS GSV (3 chars)
            + "1"                                # 85:    Telecom Spec (1:3G)
            + "1FAD"                             # 86-89: LAC (4 chars hex)
            + "944B000"                          # 90-96: CID (7 chars hex)
            + "466"                              # 97-99: MCC (3 chars)
            + "092"                              # 100-102: MNC (3 chars)
        )
    return build_packet("RD", msg_num, imei, gps_data)

def build_sc_packet(msg_num: int, imei: str) -> bytes:
    """
    建立 SC（登出）封包

    依據協定 v1.20:
      Offs 0, Len 1: 離線原由 (0:保留, 1:關機, 2:休眠, ...)
      Offs 1, Len n: 登出原因文字
    例: #SC 000 IMEI 016 1 Device.Shutdown
    """
    return build_packet("SC", msg_num, imei, "1 Monitor.Done")

# =============================================
# TCP 通訊
# =============================================

def recv_response(sock: socket.socket, timeout: float = 10.0) -> str:
    """接收 Server 回應"""
    sock.settimeout(timeout)
    try:
        data = sock.recv(4096)
        if not data:
            return ""
        return data.decode("ascii", errors="replace")
    except socket.timeout:
        return ""

def parse_commands(response: str) -> list:
    """
    解析回應中的所有命令，回傳 [(command_code, full_command), ...]
    Server 可能在一個 recv 中送多個命令，用 # 分割
    """
    commands = []
    for part in response.split("#"):
        part = part.strip()
        if len(part) >= 2:
            commands.append((part[:2], "#" + part))
    return commands

def recv_until_command(sock: socket.socket, target_cmd: str, timeout: float = 10.0, max_attempts: int = 3) -> tuple:
    """
    持續接收直到收到目標命令，或超過最大嘗試次數
    回傳: (found: bool, all_commands: list of (code, raw), target_raw: str)

    用途：Server 可能分多次送 SB 和 RC，或 RC 和 AK 分開到達
    """
    all_commands = []
    for _ in range(max_attempts):
        response = recv_response(sock, timeout)
        if not response:
            break
        cmds = parse_commands(response)
        all_commands.extend(cmds)
        logger.debug(f"    recv_until_command: 收到 {[c[0] for c in cmds]}, 目標={target_cmd}")

        for code, raw in cmds:
            if code == target_cmd:
                return True, all_commands, raw

    return False, all_commands, ""

# =============================================
# 健康檢查核心
# =============================================

def run_sink_check(host: str, port: int, imei: str, firmware_version: str, service_name: str, rd_format: str = "icar") -> dict:
    """
    執行一次 SINK Server 健康檢查

    完整流程: TCP 連線 → SA(登入) → 等 SB+RC → RD(回報位置) → 等 AK → SC(登出)
    判定: 收到 AK 代表完整協定流程通過（含 TCP、應用程式、DB 讀寫）

    回傳: {"status": "OK"/"FAIL", "response_time_ms": int, "error": str|None, "details": str}
    """
    timeout = SinkCommonConfig.CONNECT_TIMEOUT_S
    start_time = time.time()
    result = {"status": "FAIL", "response_time_ms": 0, "error": None, "details": ""}
    steps_done = []

    sock = None
    try:
        # ===== Step 1: TCP 連線 =====
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        steps_done.append("TCP_CONNECT")
        logger.info(f"  [{service_name}] [1/6] TCP 連線成功 → {host}:{port}")

        # ===== Step 2: 送 SA (登入) =====
        sa_packet = build_sa_packet(1, imei, firmware_version)
        sock.sendall(sa_packet)
        steps_done.append("SA_SENT")
        logger.info(f"  [{service_name}] [2/6] SA 已送出: {sa_packet}")

        # ===== Step 3: 等 SB 回應 =====
        found, all_cmds, _ = recv_until_command(sock, "SB", timeout, max_attempts=3)
        cmd_codes = [c[0] for c in all_cmds]

        if not found:
            result["error"] = f"SA 登入失敗，未收到 SB，收到: {cmd_codes}"
            logger.error(f"  [{service_name}] [3/6]  {result['error']}")
            return result

        steps_done.append("SB_RECEIVED")
        logger.info(f"  [{service_name}] [3/6] SB 回應收到 ")

        # ===== Step 4: 等 RC 回應（回報設定）=====
        if "RC" in cmd_codes:
            steps_done.append("RC_RECEIVED")
            logger.info(f"  [{service_name}] [4/6] RC 回報設定收到 （與 SB 同批）")
        else:
            found_rc, extra_cmds, _ = recv_until_command(sock, "RC", timeout=3, max_attempts=2)
            if found_rc:
                steps_done.append("RC_RECEIVED")
                logger.info(f"  [{service_name}] [4/6] RC 回報設定收到 （")
            else:
                logger.warning(f"  [{service_name}] [4/6] RC 未收到，繼續...")

        # ===== Step 5: 送 RD (回報位置) =====
        rd_packet = build_rd_packet(2, imei, rd_format)
        sock.sendall(rd_packet)
        steps_done.append("RD_SENT")
        logger.info(f"  [{service_name}] [5/6] RD 已送出 (format={rd_format}, {len(rd_packet)} bytes)")

        # ===== Step 6: 等 AK 回應 =====
        found_ak, ak_cmds, _ = recv_until_command(sock, "AK", timeout, max_attempts=3)
        ak_cmd_codes = [c[0] for c in ak_cmds]

        if not found_ak:
            result["error"] = f"RD 回報後未收到 AK，收到: {ak_cmd_codes}"
            logger.error(f"  [{service_name}] [6/6]  {result['error']}")
            return result

        steps_done.append("AK_RECEIVED")
        logger.info(f"  [{service_name}] [6/6] AK 回應收到  — ！")

        # ===== 送 SC (登出) — 不影響判定 =====
        try:
            sc_packet = build_sc_packet(3, imei)
            sock.sendall(sc_packet)
            steps_done.append("SC_SENT")
            logger.info(f"  [{service_name}]       SC 登出已送出")
        except Exception:
            pass

        # 完整流程通過
        result["status"] = "OK"
        result["details"] = " → ".join(steps_done)

    except socket.timeout:
        result["error"] = f"連線逾時 ({timeout}s)，已完成: {' → '.join(steps_done)}"
        logger.error(f"  [{service_name}] ✗ {result['error']}")

    except ConnectionRefusedError:
        result["error"] = f"連線被拒絕 {host}:{port}"
        logger.error(f"  [{service_name}] ✗ {result['error']}")

    except OSError as e:
        result["error"] = f"網路錯誤: {e}"
        logger.error(f"  [{service_name}] ✗ {result['error']}")

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {str(e)}"
        logger.error(f"  [{service_name}] ✗ {result['error']}")

    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass
        elapsed_ms = int((time.time() - start_time) * 1000)
        result["response_time_ms"] = elapsed_ms

    return result

def run_sink_check_with_retry(host: str, port: int, imei: str, firmware_version: str, service_name: str, rd_format: str = "icar") -> dict:
    """執行健康檢查，失敗時重試一次"""
    result = run_sink_check(host, port, imei, firmware_version, service_name, rd_format)

    if result["status"] == "OK":
        return result

    # 第一次失敗，等 5 秒後重試
    logger.warning(f"  [{service_name}] 第一次檢查失敗，5 秒後重試...")
    time.sleep(5)

    logger.info(f"  [{service_name}] === 重試第二次 ===")
    result = run_sink_check(host, port, imei, firmware_version, service_name, rd_format)

    if result["status"] == "FAIL":
        logger.error(f"  [{service_name}] 兩次檢查都失敗！")

    return result

# =============================================
# 各 SINK 監控任務
# =============================================

SINK_TARGETS = {
    "icar": {
        "config": ICarSinkConfig,
        "label": "iCar 570",
    },
    "yjgps": {
        "config": YJGPSSinkConfig,
        "label": "YJGPS 540",
    },
    "ipet": {
        "config": IPetSinkConfig,
        "label": "iPet 340",
    },
}

def check_single_sink(key: str):
    """檢查單一 SINK Server"""
    target = SINK_TARGETS[key]
    cfg = target["config"]
    label = target["label"]

    # 跳過未設定的
    if cfg.HOST.startswith("TODO"):
        logger.warning(f"[{label}] HOST 尚未設定 ({cfg.HOST})，跳過")
        return

    logger.info(f"[{label}] 開始檢查 {cfg.HOST}:{cfg.PORT} (IMEI: {cfg.TEST_IMEI})")

    result = run_sink_check_with_retry(
        host=cfg.HOST,
        port=cfg.PORT,
        imei=cfg.TEST_IMEI,
        firmware_version=cfg.FIRMWARE_VERSION,
        service_name=cfg.SERVICE_NAME,
        rd_format=cfg.RD_FORMAT,
    )

    logger.info(
        f"[{label}] 結果: {result['status']} | {result['response_time_ms']}ms"
        + (f" | {result['details']}" if result["status"] == "OK" else f" | {result['error']}")
    )

    # 寫入 DB
    try:
        write_heartbeat_log(
            service_name=cfg.SERVICE_NAME,
            status=result["status"],
            response_time_ms=result["response_time_ms"],
            error_message=result["error"],
        )
    except Exception as e:
        logger.error(f"[{label}] DB 操作失敗: {e}")

    # 兩次重試都失敗 → 立刻發 Google Chat 告警
    if result["status"] == "FAIL":
        logger.critical(f"[{label}] 兩次檢查都失敗！發送 Google Chat 告警...")
        send_google_chat_alert(
            service_name=f"{label} ({cfg.SERVICE_NAME})",
            error_message=result["error"],
            response_time_ms=result["response_time_ms"],
        )

# =============================================
# 主程式
# =============================================

def main():
    interval = SinkCommonConfig.CHECK_INTERVAL_S

    # 解析目標參數：支援 --only icar 或直接 icar
    only_target = None
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        if idx + 1 < len(sys.argv):
            only_target = sys.argv[idx + 1].lower()
    else:
        for arg in sys.argv[1:]:
            if arg.lower() in SINK_TARGETS:
                only_target = arg.lower()
                break

    if only_target and only_target not in SINK_TARGETS:
        logger.error(f"未知的目標: {only_target}，可用: {list(SINK_TARGETS.keys())}")
        sys.exit(1)

    targets = [only_target] if only_target else list(SINK_TARGETS.keys())

    logger.info("=" * 50)
    logger.info("  SINK Server Monitor 啟動")
    logger.info(f"  監控目標: {', '.join(targets)}")
    logger.info(f"  檢查間隔: {interval} 秒")
    logger.info("=" * 50)

    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"\n[{now}] ===== 開始檢查 =====")

        for key in targets:
            try:
                check_single_sink(key)
            except Exception as e:
                logger.error(f"檢查 {key} 時發生未預期錯誤: {e}")

        if "--once" in sys.argv:
            logger.info("\n--once 模式，執行完畢")
            break

        logger.info(f"下次檢查: {interval} 秒後...")
        time.sleep(interval)

if __name__ == "__main__":
    main()