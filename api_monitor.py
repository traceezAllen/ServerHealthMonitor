"""
API Server 監控腳本

支援 SOAP + REST API 健康檢查：
  - YJGPS 540: SOAP (AppWSV2.asmx) + REST (v2/api/)

監控的 API（P1 優先）：
  1. ClientRegistration   — SOAP 登入（最關鍵）
  2. GetDeviceListByAccount — SOAP 取得裝置列表
  3. GetDevicesLocation    — SOAP 取得即時位置

判定標準：
  - HTTP 200 + 回應中有合法 JSON STATUS 欄位 = OK
  - 否則 = FAIL
  - 兩次都失敗才發 Google Chat 告警

用法：
  python api_monitor.py                   # 監控所有 API（每 1 分鐘）
  python api_monitor.py --once            # 只執行一次
  python api_monitor.py --only yjgps      # 只監控 YJGPS API
"""

import json
import ssl
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

from config import ApiCommonConfig, YJGPSApiConfig, ICarApiConfig, SinkWebApiConfig
from db import write_heartbeat_log
from alert import send_google_chat_alert
from logger_setup import setup_logger

logger = setup_logger("api_monitor")

# =============================================
# SOAP 呼叫
# =============================================

def build_soap_envelope(action: str, namespace: str, params: dict) -> str:
    """組裝 SOAP XML Envelope"""
    params_xml = "\n".join(f"      <{k}>{v}</{k}>" for k, v in params.items())
    return f'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <{action} xmlns="{namespace}">
{params_xml}
    </{action}>
  </soap:Body>
</soap:Envelope>'''


def call_soap_api(url: str, namespace: str, action: str, params: dict, timeout: int = 10) -> dict:
    """
    呼叫 SOAP API，回傳 {"status": "OK"/"FAIL", "response_time_ms": int, "error": str|None, "soap_status": str}
    """
    result = {"status": "FAIL", "response_time_ms": 0, "error": None, "soap_status": ""}

    envelope = build_soap_envelope(action, namespace, params)
    ctx = ssl.create_default_context()

    req = urllib.request.Request(url, data=envelope.encode("utf-8"))
    req.add_header("Content-Type", "text/xml; charset=utf-8")
    req.add_header("SOAPAction", namespace + action)

    start = time.time()
    try:
        resp = urllib.request.urlopen(req, context=ctx, timeout=timeout)
        body = resp.read().decode("utf-8")
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed

        if resp.status != 200:
            result["error"] = f"HTTP {resp.status}"
            return result

        # 解析 SOAP 回應中的 Result
        result_tag = f"{action}Result"
        if result_tag in body:
            start_idx = body.index(result_tag) + len(result_tag) + 1
            end_idx = body.index(f"</{result_tag}")
            raw_result = body[start_idx:end_idx]
            try:
                data = json.loads(raw_result)
                if isinstance(data, dict):
                    result["soap_status"] = data.get("STATUS", "")
                else:
                    # boolean, string 等非 dict 回應（如 CheckIsMember 回傳 "false"）
                    result["soap_status"] = str(data)
                # 有回應就代表 API 正常運作
                result["status"] = "OK"
            except (json.JSONDecodeError, ValueError):
                # 非 JSON 的文字回應也算 OK（API 有回應）
                result["soap_status"] = raw_result[:50]
                result["status"] = "OK"
        else:
            result["error"] = f"回應中找不到 {result_tag}"

    except urllib.error.HTTPError as e:
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed
        result["error"] = f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed
        result["error"] = f"連線失敗: {e.reason}"
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed
        result["error"] = f"{type(e).__name__}: {str(e)}"

    return result


# =============================================
# REST API 呼叫
# =============================================

def call_rest_api(url: str, params: dict, timeout: int = 10) -> dict:
    """
    呼叫 REST API (POST, form-urlencoded)
    回傳 {"status": "OK"/"FAIL", "response_time_ms": int, "error": str|None, "api_status": str}
    """
    result = {"status": "FAIL", "response_time_ms": 0, "error": None, "api_status": ""}

    data = "&".join(f"{k}={v}" for k, v in params.items()).encode("utf-8")
    ctx = ssl.create_default_context()

    req = urllib.request.Request(url, data=data)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    start = time.time()
    try:
        resp = urllib.request.urlopen(req, context=ctx, timeout=timeout)
        body = resp.read().decode("utf-8")
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed

        if resp.status != 200:
            result["error"] = f"HTTP {resp.status}"
            return result

        # 解析 JSON 回應
        try:
            data = json.loads(body)
            result["api_status"] = data.get("STATUS", "")
            result["status"] = "OK"
        except json.JSONDecodeError:
            result["error"] = f"JSON 解析失敗: {body[:100]}"

    except urllib.error.HTTPError as e:
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed
        result["error"] = f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed
        result["error"] = f"連線失敗: {e.reason}"
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed
        result["error"] = f"{type(e).__name__}: {str(e)}"

    return result


# =============================================
# YJGPS API 檢查定義
# =============================================

def build_yjgps_api_checks() -> list:
    """建立 YJGPS 540 的 API 檢查清單"""
    cfg = YJGPSApiConfig
    ns = cfg.SOAP_NAMESPACE

    checks = []

    # P1-1: ClientRegistration（登入）
    checks.append({
        "service_name": "YJGPS_API_ClientRegistration",
        "label": "YJGPS ClientRegistration (登入)",
        "type": "soap",
        "url": cfg.SOAP_URL,
        "namespace": ns,
        "action": "ClientRegistration",
        "params": {
            "SERVER_API_VISION": "100",
            "ACCOUNT": cfg.TEST_ACCOUNT,
            "PASSWORD": cfg.TEST_PASSWORD,
            "CSYSTEM": "android",
            "PTYPE": "phone",
            "CMODEL": "ServerMonitor",
            "COSVERSION": "Monitor1.0",
            "CID": cfg.TEST_CID,
            "APP_NAME": "yjgps3g",
            "APP_VERSION": "1.0",
            "APP_PUSH_SERVER": "fcm",
            "APP_PUSH_TOKEN": cfg.TEST_FCM_TOKEN,
            "CTIMEZONE": "+0800",
        },
    })

    # P1-2: GetDeviceListByAccount（裝置列表）
    checks.append({
        "service_name": "YJGPS_API_GetDeviceList",
        "label": "YJGPS GetDeviceListByAccount (裝置列表)",
        "type": "soap",
        "url": cfg.SOAP_URL,
        "namespace": ns,
        "action": "GetDeviceListByAccount",
        "params": {
            "SERVER_API_VISION": "100",
            "ACCOUNT": cfg.TEST_ACCOUNT,
            "PASSWORD": cfg.TEST_PASSWORD,
            "CID": cfg.TEST_CID,
            "APP_NAME": "yjgps3g",
            "PAGE": "1",
        },
    })

    # P1-3: GetDevicesLocation（即時位置）
    checks.append({
        "service_name": "YJGPS_API_GetDevicesLocation",
        "label": "YJGPS GetDevicesLocation (即時位置)",
        "type": "soap",
        "url": cfg.SOAP_URL,
        "namespace": ns,
        "action": "GetDevicesLocation",
        "params": {
            "SERVER_API_VISION": "100",
            "IMEI": json.dumps([{"IMEI": cfg.TEST_IMEI}]),
        },
    })

    # --- P2: REST v2 API ---
    common_rest = {
        "ACCOUNT": cfg.TEST_ACCOUNT,
        "PASSWORD": cfg.TEST_PASSWORD,
        "CID": cfg.TEST_CID,
        "APP_NAME": "yjgps3g",
    }

    # P2-1: GetDeviceLocationHistory（歷史軌跡）
    checks.append({
        "service_name": "YJGPS_API_GetLocationHistory",
        "label": "YJGPS v2 GetDeviceLocationHistory (歷史軌跡)",
        "type": "rest",
        "url": f"{cfg.REST_BASE_URL}/GetDeviceLocationHistory",
        "params": {
            **common_rest,
            "IMEI": cfg.TEST_IMEI,
            "STIME": "202601010000",
            "ETIME": "202601010100",
            "LBSINFO": "0",
            "PAGE": "1",
        },
    })

    # P2-2: GetDeviceGeofence（電子圍欄）
    checks.append({
        "service_name": "YJGPS_API_GetDeviceGeofence",
        "label": "YJGPS v2 GetDeviceGeofence (電子圍欄)",
        "type": "rest",
        "url": f"{cfg.REST_BASE_URL}/GetDeviceGeofence",
        "params": {
            **common_rest,
            "IMEI": cfg.TEST_IMEI,
        },
    })

    # P2-3: GetLandmark（地標）
    checks.append({
        "service_name": "YJGPS_API_GetLandmark",
        "label": "YJGPS v2 GetLandmark (地標)",
        "type": "rest",
        "url": f"{cfg.REST_BASE_URL}/GetLandmark",
        "params": common_rest,
    })

    return checks


# =============================================
# iCar API 檢查定義
# =============================================

def call_gateway_api(url: str, timeout: int = 10) -> dict:
    """
    呼叫 iCar Gateway .aspx API (HTTP GET, text 回應)
    判定: HTTP 200 + 有回應內容 = OK（即使回應是 ERROR:CID 也代表 API 活著）
    回傳 {"status": "OK"/"FAIL", "response_time_ms": int, "error": str|None, "api_status": str}
    """
    result = {"status": "FAIL", "response_time_ms": 0, "error": None, "api_status": ""}
    ctx = ssl.create_default_context()

    req = urllib.request.Request(url)
    start = time.time()
    try:
        resp = urllib.request.urlopen(req, context=ctx, timeout=timeout)
        body = resp.read().decode("utf-8")
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed

        if resp.status != 200:
            result["error"] = f"HTTP {resp.status}"
            return result

        # 有回應就算 OK（ERROR:CID / EMAIL format 等都代表 Server 正常運作中）
        result["api_status"] = body.strip()[:50]
        result["status"] = "OK"

    except urllib.error.HTTPError as e:
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed
        result["error"] = f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed
        result["error"] = f"連線失敗: {e.reason}"
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed
        result["error"] = f"{type(e).__name__}: {str(e)}"

    return result


def build_icar_api_checks() -> list:
    """建立 iCar 570 的 API 檢查清單"""
    cfg = ICarApiConfig
    checks = []

    # P1-1: Auth CheckIsMember（認證登入）— 獨立 SOAP Server
    checks.append({
        "service_name": "iCar_API_CheckIsMember",
        "label": "iCar Auth CheckIsMember (認證登入)",
        "type": "soap",
        "url": cfg.AUTH_SOAP_URL,
        "namespace": cfg.AUTH_NAMESPACE,
        "action": "CheckIsMember",
        "params": {
            "sEmail": cfg.TEST_ACCOUNT,
            "Password": cfg.TEST_PASSWORD,
        },
    })

    # P1-2: iGateway Query（查詢裝置位置）
    checks.append({
        "service_name": "iCar_API_GatewayQuery",
        "label": "iCar iGateway Query (查詢位置)",
        "type": "gateway",
        "url": f"{cfg.GATEWAY_BASE_URL}/iGateway.aspx?MODE=Query&gmail={cfg.TEST_ACCOUNT}&CID={cfg.TEST_CID}&APP_NAME=icar&IMEI={cfg.TEST_IMEI}",
    })

    # P1-3: icar_GetImeiList（裝置列表）
    checks.append({
        "service_name": "iCar_API_GetImeiList",
        "label": "iCar GetImeiList (裝置列表)",
        "type": "gateway",
        "url": f"{cfg.GATEWAY_BASE_URL}/icar_GetImeiList.aspx?gmail={cfg.TEST_ACCOUNT}&CID={cfg.TEST_CID}&APP_NAME=icar",
    })

    # P2-1: GetTrackerUTCHistoryInfo（歷史軌跡）— safetrek-api
    checks.append({
        "service_name": "iCar_API_GetHistory",
        "label": "iCar GetTrackerUTCHistoryInfo (歷史軌跡)",
        "type": "gateway",
        "url": f"{cfg.GATEWAY_BASE_URL}/GetTrackerUTCHistoryInfo.aspx?gmail={cfg.TEST_ACCOUNT}&CID={cfg.TEST_CID}&APP_NAME=icar&IMEI={cfg.TEST_IMEI}&SDateTime=20260101000000&EDateTime=20260101010000",
    })

    # P1-4: icar-api.traceez.com 域名（iOS iCar App 正式版使用此域名）
    icar_domain_base = cfg.ICAR_DOMAIN_BASE_URL
    checks.append({
        "service_name": "iCar_API_iCarDomain_GetImeiList",
        "label": "iCar icar-api GetImeiList (iOS正式版域名)",
        "type": "gateway",
        "url": f"{icar_domain_base}/icar_GetImeiList.aspx?gmail={cfg.TEST_ACCOUNT}&CID={cfg.TEST_CID}&APP_NAME=icar",
    })

    return checks


# =============================================
# SinkServerWeb Device CMD API 呼叫
# =============================================

def call_device_cmd_api(url: str, cmd: str, imei: str, data: dict, timeout: int = 10) -> dict:
    """
    呼叫 SinkServerWeb Device CMD API (HTTP POST JSON)
    POST /api/v1/device/CMD
    Body: {"cmd": "SA", "imei": "...", "data": {...}}
    判定: HTTP 200 + 有回應 = OK
    """
    result = {"status": "FAIL", "response_time_ms": 0, "error": None, "api_status": ""}

    payload = json.dumps({"cmd": cmd, "imei": imei, "data": data}).encode("utf-8")
    ctx = ssl.create_default_context()

    req = urllib.request.Request(url, data=payload)
    req.add_header("Content-Type", "application/json; charset=utf-8")

    start = time.time()
    try:
        resp = urllib.request.urlopen(req, context=ctx, timeout=timeout)
        body = resp.read().decode("utf-8")
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed

        if resp.status != 200:
            result["error"] = f"HTTP {resp.status}"
            return result

        # 有回應就算 OK（Server 正常運作中）
        result["api_status"] = body.strip()[:80]
        result["status"] = "OK"

    except urllib.error.HTTPError as e:
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed
        # 400 Bad Request 也代表 Server 活著（命令格式錯才會 400）
        if e.code == 400:
            try:
                err_body = e.read().decode("utf-8")
                result["api_status"] = f"HTTP 400 (Server alive): {err_body[:50]}"
                result["status"] = "OK"
            except Exception:
                result["api_status"] = "HTTP 400 (Server alive)"
                result["status"] = "OK"
        else:
            result["error"] = f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed
        result["error"] = f"連線失敗: {e.reason}"
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        result["response_time_ms"] = elapsed
        result["error"] = f"{type(e).__name__}: {str(e)}"

    return result


def run_sinkweb_full_check() -> dict:
    """
    SinkServerWeb 整合測試: SA→RD→SC 全部通過才算 OK
    回傳 {"status": "OK"/"FAIL", "response_time_ms": int, "error": str|None, "api_status": str}
    """
    cfg = SinkWebApiConfig
    from datetime import timezone

    total_ms = 0
    steps = []

    # Step 1: SA — 登入
    sa_result = call_device_cmd_api(
        url=cfg.BASE_URL, cmd="SA", imei=cfg.TEST_IMEI,
        data={"version": "apptracker.monitor.v1"},
        timeout=ApiCommonConfig.TIMEOUT_S,
    )
    total_ms += sa_result["response_time_ms"]
    if sa_result["status"] != "OK":
        return {"status": "FAIL", "response_time_ms": total_ms, "error": f"SA 失敗: {sa_result['error']}", "api_status": ""}
    steps.append("SA:OK")

    # Step 2: RD — 回報位置
    now_utc = datetime.now(timezone.utc)
    rd_data = [{
        "Date": now_utc.strftime("%d%m%y"),
        "Time": now_utc.strftime("%H%M%S"),
        "LatPos": "2501.9154", "Lat": "N",
        "LngPos": "12127.8371", "Lng": "E",
        "GPSStatus": "A", "Speed": "0.0", "Direction": "000", "Distance": "00000",
        "GSMCSQ": "31", "Voltage": "4.05", "BatteryMode": "1",
        "StillMode": "0", "HistoryMode": "0", "ReportReason": "2",
        "SatelliteStatus": "010203040506070809101112",
        "GPSMode": "1", "HDOP": "08", "TelecomSpec": "0",
        "LAC": "12345", "CID": "6789", "MCC": "466", "MNC": "001",
        "SOS": "0", "Park": "0", "ActionMode": "0",
    }]
    rd_result = call_device_cmd_api(
        url=cfg.BASE_URL, cmd="RD", imei=cfg.TEST_IMEI,
        data=rd_data, timeout=ApiCommonConfig.TIMEOUT_S,
    )
    total_ms += rd_result["response_time_ms"]
    if rd_result["status"] != "OK":
        return {"status": "FAIL", "response_time_ms": total_ms, "error": f"RD 失敗: {rd_result['error']}", "api_status": ""}
    steps.append("RD:OK")

    # Step 3: SC — 登出
    sc_result = call_device_cmd_api(
        url=cfg.BASE_URL, cmd="SC", imei=cfg.TEST_IMEI,
        data={"reason": 2}, timeout=ApiCommonConfig.TIMEOUT_S,
    )
    total_ms += sc_result["response_time_ms"]
    if sc_result["status"] != "OK":
        return {"status": "FAIL", "response_time_ms": total_ms, "error": f"SC 失敗: {sc_result['error']}", "api_status": ""}
    steps.append("SC:OK")

    return {
        "status": "OK",
        "response_time_ms": total_ms,
        "error": None,
        "api_status": " → ".join(steps),
    }


def build_sinkweb_api_checks() -> list:
    """建立 SinkServerWeb Device CMD API 檢查清單（單一整合測試）"""
    return [{
        "service_name": "SinkWeb_DeviceCMD",
        "label": "SinkWeb SA→RD→SC (整合測試)",
        "type": "sinkweb_full",
    }]


# =============================================
# 核心檢查邏輯
# =============================================

def run_api_check(check: dict) -> dict:
    """執行單一 API 檢查"""
    timeout = ApiCommonConfig.TIMEOUT_S

    if check["type"] == "soap":
        return call_soap_api(
            url=check["url"],
            namespace=check["namespace"],
            action=check["action"],
            params=check["params"],
            timeout=timeout,
        )
    elif check["type"] == "rest":
        return call_rest_api(
            url=check["url"],
            params=check["params"],
            timeout=timeout,
        )
    elif check["type"] == "gateway":
        return call_gateway_api(
            url=check["url"],
            timeout=timeout,
        )
    elif check["type"] == "device_cmd":
        return call_device_cmd_api(
            url=check["url"],
            cmd=check["cmd"],
            imei=check["imei"],
            data=check["data"],
            timeout=timeout,
        )
    elif check["type"] == "sinkweb_full":
        return run_sinkweb_full_check()

    return {"status": "FAIL", "response_time_ms": 0, "error": "未知的 API 類型"}


def run_api_check_with_retry(check: dict) -> dict:
    """執行 API 檢查，失敗時重試一次"""
    result = run_api_check(check)
    if result["status"] == "OK":
        return result

    logger.warning(f"  [{check['service_name']}] 第一次檢查失敗，3 秒後重試...")
    time.sleep(3)

    logger.info(f"  [{check['service_name']}] === 重試第二次 ===")
    result = run_api_check(check)
    if result["status"] == "FAIL":
        logger.error(f"  [{check['service_name']}] 兩次檢查都失敗！")

    return result


def check_single_api(check: dict):
    """檢查單一 API 並寫入 DB + 告警"""
    label = check["label"]
    service_name = check["service_name"]

    logger.info(f"[{label}] 開始檢查...")

    result = run_api_check_with_retry(check)

    api_st = result.get("soap_status") or result.get("api_status") or ""
    status_info = f" (STATUS={api_st})" if api_st else ""

    if result["status"] == "OK":
        logger.info(f"[{label}] OK | {result['response_time_ms']}ms{status_info}")
    else:
        logger.error(f"[{label}] FAIL | {result['response_time_ms']}ms | {result['error']}")

    # 寫入 DB
    try:
        write_heartbeat_log(
            service_name=service_name,
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
            service_name=f"{label} ({service_name})",
            error_message=result["error"],
            response_time_ms=result["response_time_ms"],
        )


# =============================================
# API 目標定義
# =============================================

API_TARGETS = {
    "yjgps": {
        "label": "YJGPS 540 API",
        "build_checks": build_yjgps_api_checks,
    },
    "icar": {
        "label": "iCar 570 API",
        "build_checks": build_icar_api_checks,
    },
    "sinkweb": {
        "label": "SinkServerWeb Device CMD API",
        "build_checks": build_sinkweb_api_checks,
    },
}


# =============================================
# 主程式
# =============================================

def main():
    interval = ApiCommonConfig.CHECK_INTERVAL_S

    # 解析目標參數：支援 --only icar 或直接 icar
    only_target = None
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        if idx + 1 < len(sys.argv):
            only_target = sys.argv[idx + 1].lower()
    else:
        # 直接寫目標名稱，如: python api_monitor.py --once icar
        for arg in sys.argv[1:]:
            if arg.lower() in API_TARGETS:
                only_target = arg.lower()
                break

    if only_target and only_target not in API_TARGETS:
        logger.error(f"未知的目標: {only_target}，可用: {list(API_TARGETS.keys())}")
        sys.exit(1)

    targets = [only_target] if only_target else list(API_TARGETS.keys())

    logger.info("=" * 50)
    logger.info("  API Server Monitor 啟動")
    logger.info(f"  監控目標: {', '.join(targets)}")
    logger.info(f"  檢查間隔: {interval} 秒")
    logger.info("=" * 50)

    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"\n[{now}] ===== 開始檢查 =====")

        for key in targets:
            target = API_TARGETS[key]
            checks = target["build_checks"]()
            logger.info(f"--- {target['label']} ({len(checks)} 支 API) ---")

            for check in checks:
                try:
                    check_single_api(check)
                except Exception as e:
                    logger.error(f"檢查 {check['service_name']} 時發生未預期錯誤: {e}")

        if "--once" in sys.argv:
            logger.info("\n--once 模式，執行完畢")
            break

        logger.info(f"下次檢查: {interval} 秒後...")
        time.sleep(interval)


if __name__ == "__main__":
    main()
