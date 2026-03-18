import os
from dotenv import load_dotenv

load_dotenv()


class MonitorDBConfig:
    HOST = os.getenv("MONITOR_DB_HOST", "3.105.244.207")
    NAME = os.getenv("MONITOR_DB_NAME", "ServerMonitor")
    USER = os.getenv("MONITOR_DB_USER", "sinomostw")
    PASSWORD = os.getenv("MONITOR_DB_PASSWORD", "02Tracker")


class AlertConfig:
    GOOGLE_CHAT_WEBHOOK = os.getenv("GOOGLE_CHAT_WEBHOOK", "")


class SinkCommonConfig:
    CONNECT_TIMEOUT_S = int(os.getenv("SINK_CONNECT_TIMEOUT_S", 10))
    CHECK_INTERVAL_S = int(os.getenv("SINK_CHECK_INTERVAL_S", 300))


class ICarSinkConfig:
    HOST = os.getenv("ICAR_SINK_HOST", "TODO_ASK_ENGINEER")
    PORT = int(os.getenv("ICAR_SINK_PORT", 6978))
    TEST_IMEI = os.getenv("ICAR_SINK_TEST_IMEI", "10000000000002")
    SERVICE_NAME = "iCarSink(570)"
    FIRMWARE_VERSION = "iCar.monitor.v1.0"  # 必須以 "iCar." 開頭，否則 Server 拒絕登入
    RD_FORMAT = "icar"  # RD 封包格式: LEN=103, 日期 DDMMYY (UTC), 封包總長 127 bytes


class YJGPSSinkConfig:
    HOST = os.getenv("YJGPS_SINK_HOST", "safetrekawssink.traceez.com")
    PORT = int(os.getenv("YJGPS_SINK_PORT", 6971))
    TEST_IMEI = os.getenv("YJGPS_SINK_TEST_IMEI", "10000000000002")
    SERVICE_NAME = "YJGPSSink(540)"
    FIRMWARE_VERSION = "MSP540_v1.0"
    RD_FORMAT = "yjgps"  # RD 封包格式: LEN=137, 日期 DDMMYY (UTC), GPS GSA=48 chars, 封包總長 161 bytes


class IPetSinkConfig:
    HOST = os.getenv("IPET_SINK_HOST", "TODO_ASK_ENGINEER")
    PORT = int(os.getenv("IPET_SINK_PORT", 6970))
    TEST_IMEI = os.getenv("IPET_SINK_TEST_IMEI", "10000000000002")
    SERVICE_NAME = "ipetSink(340)"
    FIRMWARE_VERSION = "MSP340_v1.0"
    RD_FORMAT = "ipet"  # iPet 的 RD 格式待確認


# =============================================
# API Monitor 設定
# =============================================

class ApiCommonConfig:
    TIMEOUT_S = int(os.getenv("API_TIMEOUT_S", 10))
    CHECK_INTERVAL_S = int(os.getenv("API_CHECK_INTERVAL_S", 60))


class YJGPSApiConfig:
    """YJGPS 540 SOAP + REST API 設定"""
    SOAP_URL = os.getenv("YJGPS_SOAP_URL", "https://yjgps-api.yjgps.com.tw:443/AppWSV2.asmx")
    REST_BASE_URL = os.getenv("YJGPS_REST_BASE_URL", "https://yjgps-api.yjgps.com.tw/v2/api")
    SOAP_NAMESPACE = "https://yjgps-api.yjgps.com.tw/"
    TEST_ACCOUNT = os.getenv("YJGPS_TEST_ACCOUNT", "")
    TEST_PASSWORD = os.getenv("YJGPS_TEST_PASSWORD", "")
    TEST_IMEI = os.getenv("YJGPS_API_TEST_IMEI", "100000000000002")
    TEST_CID = os.getenv("YJGPS_TEST_CID", "b91c4ca91f984b908d3c059e8ab04a1d")
    TEST_FCM_TOKEN = os.getenv("YJGPS_TEST_FCM_TOKEN", "dLWXzFayS1O4_rZ3tCRrPG:APA91bHijSkAV4Xhkqk5agWG5jDaIiaYL_TZovFwOHft2rRmVAdpJDR_nvJJAGb-ctYnM_zqJaunkLZaByOBke_VhqsvD6-XB12U9D55HTX8o0jYYlRFAos")


class ICarApiConfig:
    """iCar 570 API 設定 — Auth SOAP + Tracker .aspx"""
    # Auth 認證 (獨立 SOAP Server)
    AUTH_SOAP_URL = os.getenv("ICAR_AUTH_SOAP_URL", "https://traceez-auth.traceez.com/WSAccount.asmx")
    AUTH_NAMESPACE = "https://traceez-auth.traceez.com/"
    # Tracker API — SafeTrek 域名 (Android SafeTrek App 使用)
    GATEWAY_BASE_URL = os.getenv("ICAR_GATEWAY_BASE_URL", "https://safetrek-api.traceez.com/PROGRAM/iserver")
    # Tracker API — iCar 域名 (iOS iCar App 正式版使用)
    ICAR_DOMAIN_BASE_URL = os.getenv("ICAR_DOMAIN_BASE_URL", "https://icar-api.traceez.com/PROGRAM/iserver")
    # 測試帳號
    TEST_ACCOUNT = os.getenv("ICAR_TEST_ACCOUNT", "0000002")
    TEST_PASSWORD = os.getenv("ICAR_TEST_PASSWORD", "12345678")
    TEST_IMEI = os.getenv("ICAR_API_TEST_IMEI", "100000000000002")
    TEST_CID = os.getenv("ICAR_TEST_CID", "server-monitor-001")


class SinkWebApiConfig:
    """SinkServerWeb API 設定 — AppTracker 使用的 HTTP Device CMD API"""
    BASE_URL = os.getenv("SINKWEB_API_URL", "https://sinkweb.traceez.com/api/v1/device/CMD")
    TEST_IMEI = os.getenv("SINKWEB_TEST_IMEI", "999886000000013")


# =============================================
# DB Monitor 設定
# =============================================

class DbCommonConfig:
    TIMEOUT_S = int(os.getenv("DB_CHECK_TIMEOUT_S", 10))
    CHECK_INTERVAL_S = int(os.getenv("DB_CHECK_INTERVAL_S", 300))


class ICarDbConfig:
    """iCar 570 資料庫"""
    HOST = os.getenv("ICAR_DB_HOST", "3.105.244.207")
    NAME = os.getenv("ICAR_DB_NAME", "TK_MSP570")
    USER = os.getenv("ICAR_DB_USER", "sinomostw")
    PASSWORD = os.getenv("ICAR_DB_PASSWORD", "02Tracker")
    SERVICE_NAME = "DB_iCar_Tracker"


class YJGPSDbConfig:
    """YJGPS 540 資料庫"""
    HOST = os.getenv("YJGPS_DB_HOST", "3.105.244.207")
    NAME = os.getenv("YJGPS_DB_NAME", "YJ_TK2012")
    USER = os.getenv("YJGPS_DB_USER", "sinomostw")
    PASSWORD = os.getenv("YJGPS_DB_PASSWORD", "02Tracker")
    SERVICE_NAME = "DB_YJGPS_Tracker"


class IPetDbConfig:
    """iPet 340 資料庫"""
    HOST = os.getenv("IPET_DB_HOST", "3.105.244.207")
    NAME = os.getenv("IPET_DB_NAME", "TK_MSP340")
    USER = os.getenv("IPET_DB_USER", "sinomostw")
    PASSWORD = os.getenv("IPET_DB_PASSWORD", "02Tracker")
    SERVICE_NAME = "DB_iPet_Tracker"
