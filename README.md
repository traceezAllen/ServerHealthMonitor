# ServerMonitor

Server 監控系統 — 監控 SINK Server、Web API、Database 是否活著。

## 資料庫架構

使用獨立資料庫 `ServerMonitor`，建在 `3.105.244.207`。

### 資料表

| 資料表 | 用途 |
|---|---|
| `Monitor_Category` | 系統分類（YJGPS / iCar / iPet / FCM / Payment 等 8 個分類） |
| `Monitor_Service` | 被監控的服務（每支程式/API/DB 各一筆，含 endpoint、檢查頻率、超時設定） |
| `Monitor_HeartbeatLog` | 每次檢查紀錄（含回應時間、錯誤訊息），已建索引加速查詢 |
| `Monitor_ServiceStatus` | 各服務即時狀態（一筆一服務，快速查「現在誰掛了」不用翻 Log） |

### 關聯圖

```
Monitor_Category (1) ──→ (N) Monitor_Service (1) ──→ (N) Monitor_HeartbeatLog
                                    │
                                    └──→ (1) Monitor_ServiceStatus
```


## SINK Server 監控 (`sink_monitor.py`)

透過 TCP Socket 模擬裝置連線，測試 SINK Server 完整協定流程是否正常。

### 監控的 SINK Server

| 產品 | Service Name | TCP Port | Domain | 測試 IMEI | 狀態 |
|---|---|---|---|---|---|
| iCar 570 | `iCarSink(570)` | 6930 | `safetrekawssink.traceez.com` | `100000000000002` |  已完成 |
| YJGPS 540 | `YJGPSSink(540)` | 6971 | `safetrekawssink.traceez.com` | `100000000000002` |  已完成 |
| iPet 340 | `ipetSink(340)` | 6970 | (待確認) | `100000000000002` |  待測試 |

### 測試流程

三個 SINK Server 使用相同的 TCP 協定格式：

```
封包格式: #[CommandCode:2][MsgNum:3][IMEICode:15][LenOfMsg:3][MSG:variable]
```

**完整 6 步驟測試流程：**

```
1. [1/6] TCP 連線到 SINK Server (host:port)
   ↓
2. [2/6] 送 SA（登入）— MSG = 韌體版本
   例: #SA001100000000000002017iCar.monitor.v1.0
   ↓
3. [3/6] 等 SB 回應（登入成功）
   Server 會查 IMEITable + Tracker table + 驗證啟用/付費
   ↓
4. [4/6] 等 RC 回應（回報設定）
   可能跟 SB 同批或分開到達
   ↓
5. [5/6] 送 RD（回報 GPS 位置） 必須用 UTC 時間
   iCar:  #RD002100000000000002103... (127 bytes)
   YJGPS: #RD002100000000000002137... (161 bytes)
   ↓
6. [6/6] 等 AK 回應（Server 確認收到 RD）
   ↓
   送 SC（登出）— 不影響判定
   ↓
 收到 AK = 完整流程通過（TCP + 應用程式 + DB 讀寫 都正常）
```

### RD 封包格式

 **RD 的日期時間必須使用 UTC**，若送本地時間（如 UTC+8）Server 會判定為 OVERLOG 而拒絕回 AK。

**iCar 570 格式（LEN=103，封包總長 127 bytes）：**

| Offset | Len | 說明 | 範例值 |
|---|---|---|---|
| 0 | 6 | 日期 DDMMYY (UTC) | `170326` |
| 6 | 6 | 時間 HHMMSS (UTC) | `111242` |
| 12 | 10 | 緯度+N/S | `2501.9154N` |
| 22 | 11 | 經度+E/W | `12114.2088E` |
| 33 | 1 | 定位旗標 (A=已定位) | `A` |
| 34 | 5 | 速度 (knots) | `0.000` |
| 39 | 3 | 方位 (000~359) | `000` |
| 42 | 5 | 距離 (m) | `00020` |
| 47 | 2 | GSM CSQ | `19` |
| 49 | 4 | 電池電壓 | `4.29` |
| 53 | 1 | 電源模式 | `4` |
| 54 | 1 | 運作情形 | `0` |
| 55 | 1 | 暫存回報(LOG) | `0` |
| 56 | 1 | 回報原由 | `2` |
| 57 | 1 | ID 身份欄位 | `1` |
| 58 | 24 | GPS GSA 衛星資料 | `5YFWITLSOTQYT20000000000` |
| 82 | 3 | GPS GSV | `302` |
| 85 | 1 | 電信規格 (1=3G) | `1` |
| 86 | 4 | LAC (hex) | `1FAD` |
| 90 | 7 | CID (hex) | `944B000` |
| 97 | 3 | MCC | `466` |
| 100 | 3 | MNC | `092` |

**YJGPS 540 格式（LEN=137，封包總長 161 bytes）：**

| Offset | Len | 說明 | 範例值 |
|---|---|---|---|
| 0 | 6 | 日期 DDMMYY (UTC) | `170326` |
| 6 | 6 | 時間 HHMMSS (UTC) | `111242` |
| 12 | 10 | 緯度+N/S | `2501.9154N` |
| 22 | 11 | 經度+E/W | `12114.2088E` |
| 33 | 5 | 速度 (knots) | `0.063` |
| 38 | 3 | 方位 (000~359) | `000` |
| 41 | 5 | 距離 (m) | `00002` |
| 46 | 1 | 定位旗標 (A=已定位) | `A` |
| 47 | 1 | SOS 狀態 | `0` |
| 48 | 1 | CASE 偵測旗標 | `0` |
| 49 | 2 | GSM CSQ | `19` |
| 51 | 4 | 電池電壓 | `4.29` |
| 55 | 1 | 電源模式 | `4` |
| 56 | 1 | 靜止逾時狀態 | `0` |
| 57 | 1 | 暫存回報(DataLog) | `0` |
| 58 | 1 | 震動/移動旗標 | `0` |
| 59 | 9 | Reserved | `000000000` |
| 68 | 48 | GPS GSA 衛星資料 | `5YFWITLSOTQYT2000...` |
| 116 | 3 | GPS GSV | `302` |
| 119 | 1 | 電信規格 (1=3G) | `1` |
| 120 | 4 | LAC (hex) | `1FAD` |
| 124 | 7 | CID (hex) | `123944B` |
| 131 | 3 | MCC | `466` |
| 134 | 3 | MNC | `092` |

**iCar vs YJGPS 主要差異：**

| 項目 | iCar 570 (LEN=103) | YJGPS 540 (LEN=137) |
|---|---|---|
| 韌體版本 | 必須以 `iCar.` 開頭 | `MSP540_v1.0` |
| 定位旗標位置 | Offset 33 (速度前) | Offset 46 (距離後) |
| GPS GSA 長度 | 24 chars | 48 chars |
| 額外欄位 | 回報原由、ID身份 | SOS、CASE、靜止、震動、Reserved(9) |
| 日期時間 | UTC DDMMYY HHMMSS | UTC DDMMYY HHMMSS |

### 測試 IMEI 注意事項

測試用 IMEI `100000000000002` 需在對應的資料庫中設定：
- **IMEITable**: SA 登入時自動建立（不需手動）
- **Tracker table**: 需手動補齊 **ICCID** 欄位，否則 RD 會被 Server 靜默丟棄不回 AK

### 失敗處理

1. 第一次失敗 → 等 5 秒重試
2. 第二次也失敗 → 寫入 DB（FAIL）+ **立刻發送 Google Chat 告警**

### 使用方式

```bash
# 啟動 venv
cd /develop/ServerMonitor
source venv/bin/activate

# 監控所有 SINK（每 5 分鐘）
python sink_monitor.py

# 只執行一次（測試用）
python sink_monitor.py --once

# 只監控特定 SINK
python sink_monitor.py --only icar
python sink_monitor.py --only yjgps
python sink_monitor.py --only ipet
```

### 測試失敗告警

修改 `.env` 的 port 指到未開放的 port，即可模擬 Server 掛掉：
```
ICAR_SINK_PORT=9999
```
會觸發：TCP 連線失敗 → 重試 → 再失敗 → DB 寫入 FAIL → Google Chat 告警。測完記得改回來。

---

## Server_SINK 程式清單

### iCar 570 系列
| 程式 | 說明 | Port |
|---|---|---|
| ICarSink / iCarSink_V2 | GPS 資料接收 Server | TCP 6930 |
| iCarHeartbeatMonitor | 心跳監控 | — |
| ICarManager | 管理介面（WinForms） | — |
| PN_iCar | 推播服務 | — |
| PN_iCar_IOS | iOS 推播服務 | — |
| PN_iCar_IOS(android)_v2 | iOS/Android 推播服務 V2 | — |

### YJGPS 540 系列
| 程式 | 說明 | Port |
|---|---|---|
| 540Sink_V1 / 540Sink_V2 | GPS 資料接收 Server | TCP 6971 |
| 540Sink_V2_singleR | GPS 資料接收 + SingleR | TCP 6971 |
| 540HeartbeatMonitor | 心跳監控 | — |
| YJManager | 管理介面（WinForms） | — |
| PN_YJGPS_IOS | iOS 推播服務 | — |
| PN_YJGPS_IOS(android)_v2 | iOS/Android 推播服務 V2 | — |
| PN_YJGPS_android | Android 推播服務 | — |

### iPet 340 系列
| 程式 | 說明 | Port |
|---|---|---|
| 340Sink_V1 / 340Sink_V2 | GPS 資料接收 Server | TCP 6970 |
| 340SinkForUDP | UDP 資料接收 | UDP 5960 |
| iPetHeartbeatMonitor | 心跳監控 | — |
| iPetManager | 管理介面（WinForms） | — |
| PN_iPet | 推播服務 | — |
| PN_iPet_IOS(android)_v2 | iOS/Android 推播服務 V2 | — |

### 其他
| 程式 | 說明 |
|---|---|
| ControlNode | 節點間通訊服務 |

---

## 專案結構

```
ServerMonitor/
├── .env                        ← 設定檔（不入 git）
├── .gitignore
├── config.py                   ← 讀取環境變數設定
├── db.py                       ← 共用 DB 操作（寫 HeartbeatLog、更新 ServiceStatus）
├── alert.py                    ← Google Chat 告警通知
├── logger_setup.py             ← Log 設定（logs/ 目錄，14天自動刪除）
├── sink_monitor.py             ← SINK TCP 監控（iCar/YJGPS/iPet）
├── api_monitor.py              ← API Health Check（TODO）
├── db_monitor.py               ← DB Health Check（TODO）
├── ServerMonitor_CreateDB.sql  ← SSMS 建立資料庫 SQL
├── requirements.txt
├── README.md
├── logs/                       ← Log 檔案（不入 git，14天自動刪除）
└── venv/                       ← Python 虛擬環境（不入 git）
```

---

## 告警設定

告警發送到 Google Chat，Webhook URL 設定在 `.env` 的 `GOOGLE_CHAT_WEBHOOK`。

觸發條件：兩次檢查都失敗時立刻發送告警，不等累計（避免 Server 掛了還要等多個 cycle 才通知）。
