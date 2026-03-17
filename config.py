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
