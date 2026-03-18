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
| iPet 340 | `ipetSink(340)` | 6969 | `safetrekawssink.traceez.com` | `100000000000002` |  已完成 |

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

**iPet 340 格式（LEN=103，封包總長 127 bytes）：**

> iPet 340 目前使用與 iCar 570 相同的 RD 封包格式（LEN=103）。

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

**三種產品 RD 格式比較：**

| 項目 | iCar 570 (LEN=103) | YJGPS 540 (LEN=137) | iPet 340 (LEN=103) |
|---|---|---|---|
| 韌體版本 | 必須以 `iCar.` 開頭 | `MSP540_v1.0` | `MSP340_v1.0` |
| 定位旗標位置 | Offset 33 (速度前) | Offset 46 (距離後) | Offset 33 (同 iCar) |
| GPS GSA 長度 | 24 chars | 48 chars | 24 chars (同 iCar) |
| 額外欄位 | 回報原由、ID身份 | SOS、CASE、靜止、震動、Reserved(9) | 同 iCar |
| 日期時間 | UTC DDMMYY HHMMSS | UTC DDMMYY HHMMSS | UTC DDMMYY HHMMSS |
| 封包總長 | 127 bytes | 161 bytes | 127 bytes |

### 測試 IMEI 注意事項

測試用 IMEI `100000000000002` 需注意訂單是否過期：


### 失敗處理

1. 第一次失敗 → 等 5 秒重試
2. 第二次也失敗 → 寫入 DB（FAIL）+ **發送 Google Chat 警告**

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

### 測試失敗警告

修改 `.env` 的 port 指到未開放的 port，即可模擬 Server 掛掉：
```
ICAR_SINK_PORT=9999
```
會觸發：TCP 連線失敗 → 重試 → 再失敗 → DB 寫入 FAIL → Google Chat 告警。測完記得改回來。

---

## API Server 監控 (`api_monitor.py`)

透過 SOAP / REST API 呼叫，測試 Web API 是否正常回應。

### YJGPS 540 API

**SOAP API：**

| Service Name | API | 說明 | 用於 |
|---|---|---|---|
| `YJGPS_API_ClientRegistration` | `ClientRegistration` | 登入驗證 | Android / iOS / Web |
| `YJGPS_API_GetDeviceList` | `GetDeviceListByAccount` | 取得裝置列表 | Android / iOS / Web |
| `YJGPS_API_GetDevicesLocation` | `GetDevicesLocation` | 取得即時位置 | Android / iOS / Web |

**REST v2 API：**

| Service Name | API | 說明 | 用於 |
|---|---|---|---|
| `YJGPS_API_GetLocationHistory` | `GetDeviceLocationHistory` | 歷史軌跡 | Android / iOS |
| `YJGPS_API_GetDeviceGeofence` | `GetDeviceGeofence` | 電子圍欄 | Android / iOS |
| `YJGPS_API_GetLandmark` | `GetLandmark` | 地標 | Android / iOS |

**API 設定：**

| 項目 | 值 |
|---|---|
| SOAP Endpoint | `https://yjgps-api.yjgps.com.tw/AppWSV2.asmx` |
| REST Endpoint | `https://yjgps-api.yjgps.com.tw/v2/api/` |
| 測試帳號 | `.env` 中的 `YJGPS_TEST_ACCOUNT` / `YJGPS_TEST_PASSWORD` |
| 檢查間隔 | 60 秒 |
| 判定標準 | HTTP 200 + 回應含 STATUS 欄位 = OK（不管 STATUS 值） |

### iCar 570 API

iCar 架構跟 YJGPS 不同 — Auth 是獨立 SOAP Server，Tracker 操作用 .aspx Query String：

**Auth SOAP：**

| Service Name | API | Domain | 說明 | 用於 |
|---|---|---|---|---|
| `iCar_API_CheckIsMember` | `CheckIsMember` | `traceez-auth.traceez.com` | 認證登入 | iOS / Android / Web |

**Tracker Gateway .aspx：**

| Service Name | API | Domain | 說明 | 用於 |
|---|---|---|---|---|
| `iCar_API_GatewayQuery` | `iGateway.aspx?MODE=Query` | `safetrek-api.traceez.com` | 查詢裝置位置 | iOS / Android |
| `iCar_API_GetImeiList` | `icar_GetImeiList.aspx` | `safetrek-api.traceez.com` | 裝置列表 | iOS / Android |

**Tracker Gateway .aspx：**

| Service Name | API | Domain | 說明 | 用於 |
|---|---|---|---|---|
| `iCar_API_GetHistory` | `GetTrackerUTCHistoryInfo.aspx` | `safetrek-api.traceez.com` | 歷史軌跡 | iOS / Android |

**iCar API 設定：**

| 項目 | 值 |
|---|---|
| Auth Endpoint | `https://traceez-auth.traceez.com/WSAccount.asmx` |
| Gateway Endpoint | `https://safetrek-api.traceez.com/PROGRAM/iserver/` |
| 判定標準 | HTTP 200 + 有回應內容 = OK（ERROR:CID 等錯誤回應也代表 API 活著） |

### 使用方式

```bash
# 監控所有 API（每 1 分鐘）
python api_monitor.py

# 只執行一次（測試用）
python api_monitor.py --once

# 只監控特定產品
python api_monitor.py --only yjgps
python api_monitor.py --only icar
```

### SinkServerWeb (AppTracker)

AppTracker App 使用的 HTTP Device CMD API（走 HTTP 而非 TCP Socket）：

| Service Name | API | Domain | 說明 |
|---|---|---|---|
| `SinkWeb_DeviceCMD` | `/api/v1/Device/CMD` | `sinkweb.traceez.com` | 模擬 SA→RD→SC 完整流程 |

測試 IMEI：`999886000000013`

### 失敗處理

同 SINK Monitor：第一次失敗等 3 秒重試，兩次都失敗 → DB 寫入 FAIL + Google Chat警告。

---

## DB Server 監控 (`db_monitor.py`)

連線到各產品資料庫，`SELECT COUNT(*) FROM Tracker` 確認 DB 活著且有資料。

### 監控的資料庫

| 產品 | Service Name | Database | Host | 檢查內容 |
|---|---|---|---|---|
| iCar 570 | `DB_iCar_Tracker` | `TK_MSP570` | `3.105.244.207` | Tracker 筆數 > 0 |
| YJGPS 540 | `DB_YJGPS_Tracker` | `YJ_TK2012` | `3.105.244.207` | Tracker 筆數 > 0 |
| iPet 340 | `DB_iPet_Tracker` | `TK_MSP340` | `3.105.244.207` | Tracker 筆數 > 0 |

### 判定標準

- 連線成功 + `SELECT COUNT(*) FROM Tracker` 回傳 > 0 = **OK**
- 連線失敗或查無資料 = **FAIL**

### 使用方式

```bash
# 監控所有 DB（每 5 分鐘）
python db_monitor.py

# 只執行一次（測試用）
python db_monitor.py --once

# 只監控特定產品
python db_monitor.py --once icar
python db_monitor.py --once yjgps
python db_monitor.py --once ipet
```

### 失敗處理

同 SINK Monitor：第一次失敗等 3 秒重試，兩次都失敗 → DB 寫入 FAIL + 立刻 Google Chat 告警。

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
| 340Sink_V1 / 340Sink_V2 | GPS 資料接收 Server | TCP 6969 |
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
├── api_monitor.py              ← API 監控（YJGPS SOAP + REST / iCar Gateway / SinkWeb）
├── db_monitor.py               ← DB 監控（Tracker 表連線 + 筆數檢查）
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

---

## 部署到 IIS Server

### 1. 環境準備

```powershell
# 在 IIS Server 上安裝 Python (3.10+)
# 下載: https://www.python.org/downloads/

# 確認 Python 已加入 PATH
python --version

# 建立專案目錄（例如 D:\ServerMonitor）
mkdir D:\ServerMonitor
# 將整個專案複製到此目錄
```

### 2. 安裝 Python 環境

```powershell
cd D:\ServerMonitor

# 建立虛擬環境
python -m venv venv

# 啟用虛擬環境
.\venv\Scripts\activate

# 安裝套件
pip install -r requirements.txt
```

### 3. 設定 .env

```powershell
# 複製並編輯 .env
copy .env.example .env
notepad .env
```

確認以下設定正確：
- `MONITOR_DB_HOST` / `MONITOR_DB_USER` / `MONITOR_DB_PASSWORD`
- `GOOGLE_CHAT_WEBHOOK`
- 各 DB Host / Name / 帳密

### 4. 測試執行

```powershell
# 先單次執行確認可用
.\venv\Scripts\python sink_monitor.py --once
.\venv\Scripts\python api_monitor.py --once
.\venv\Scripts\python db_monitor.py --once
```

### 5. 用 NSSM 設定背景服務（推薦）

使用 [NSSM](https://nssm.cc/) (Non-Sucking Service Manager) 將 Python 腳本註冊為 Windows Service：

```powershell
# 下載 NSSM: https://nssm.cc/download
# 解壓後將 nssm.exe 放到 D:\Tools\nssm\ 或加入 PATH

# 註冊 SINK Monitor 服務
nssm install ServerMonitor-SINK "D:\ServerMonitor\venv\Scripts\python.exe" "D:\ServerMonitor\sink_monitor.py"
nssm set ServerMonitor-SINK AppDirectory "D:\ServerMonitor"
nssm set ServerMonitor-SINK DisplayName "Server Monitor - SINK"
nssm set ServerMonitor-SINK Description "SINK TCP 連線監控 (iCar/YJGPS/iPet)"
nssm set ServerMonitor-SINK Start SERVICE_AUTO_START
nssm set ServerMonitor-SINK AppStdout "D:\ServerMonitor\logs\sink_service.log"
nssm set ServerMonitor-SINK AppStderr "D:\ServerMonitor\logs\sink_service_err.log"

# 註冊 API Monitor 服務
nssm install ServerMonitor-API "D:\ServerMonitor\venv\Scripts\python.exe" "D:\ServerMonitor\api_monitor.py"
nssm set ServerMonitor-API AppDirectory "D:\ServerMonitor"
nssm set ServerMonitor-API DisplayName "Server Monitor - API"
nssm set ServerMonitor-API Description "API Health Check 監控 (SOAP/REST/Gateway)"
nssm set ServerMonitor-API Start SERVICE_AUTO_START
nssm set ServerMonitor-API AppStdout "D:\ServerMonitor\logs\api_service.log"
nssm set ServerMonitor-API AppStderr "D:\ServerMonitor\logs\api_service_err.log"

# 註冊 DB Monitor 服務
nssm install ServerMonitor-DB "D:\ServerMonitor\venv\Scripts\python.exe" "D:\ServerMonitor\db_monitor.py"
nssm set ServerMonitor-DB AppDirectory "D:\ServerMonitor"
nssm set ServerMonitor-DB DisplayName "Server Monitor - DB"
nssm set ServerMonitor-DB Description "DB Health Check 監控 (Tracker 連線檢查)"
nssm set ServerMonitor-DB Start SERVICE_AUTO_START
nssm set ServerMonitor-DB AppStdout "D:\ServerMonitor\logs\db_service.log"
nssm set ServerMonitor-DB AppStderr "D:\ServerMonitor\logs\db_service_err.log"

# 啟動服務
nssm start ServerMonitor-SINK
nssm start ServerMonitor-API
nssm start ServerMonitor-DB
```

### 6. 管理服務

```powershell
# 查看狀態
nssm status ServerMonitor-SINK
nssm status ServerMonitor-API
nssm status ServerMonitor-DB

# 停止 / 重啟
nssm stop ServerMonitor-SINK
nssm restart ServerMonitor-API

# 修改設定（會打開 GUI）
nssm edit ServerMonitor-SINK

# 移除服務
nssm remove ServerMonitor-SINK confirm
```

### 7. 架設監控儀表板（IIS + Flask）

使用 IIS 反向代理 Flask：

```powershell
# 安裝 IIS URL Rewrite + ARR (Application Request Routing)
# 下載: https://www.iis.net/downloads/microsoft/url-rewrite
# 下載: https://www.iis.net/downloads/microsoft/application-request-routing

# 用 NSSM 註冊 Flask Web 服務
nssm install ServerMonitor-Web "D:\ServerMonitor\venv\Scripts\python.exe" "D:\ServerMonitor\app.py"
nssm set ServerMonitor-Web AppDirectory "D:\ServerMonitor"
nssm set ServerMonitor-Web DisplayName "Server Monitor - Web Dashboard"
nssm set ServerMonitor-Web Start SERVICE_AUTO_START
nssm start ServerMonitor-Web
```

在 IIS 建立網站 `Server-Monitor.traceez.com`，設定反向代理到 `http://localhost:5050`：

1. IIS Manager → Sites → Add Website
2. Site name: `ServerMonitor`
3. Binding: `Server-Monitor.traceez.com` (HTTP 80 / HTTPS 443)
4. 在該 Site 底下新增 `web.config` 做 Reverse Proxy：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="ReverseProxy" stopProcessing="true">
          <match url="(.*)" />
          <action type="Rewrite" url="http://localhost:5050/{R:1}" />
        </rule>
      </rules>
    </rewrite>
  </system.webServer>
</configuration>
```

### 服務清單

| Windows Service | 程式 | 說明 |
|---|---|---|
| `ServerMonitor-SINK` | `sink_monitor.py` | SINK TCP 監控 (每 5 分鐘) |
| `ServerMonitor-API` | `api_monitor.py` | API Health 監控 (每 1 分鐘) |
| `ServerMonitor-DB` | `db_monitor.py` | DB 連線監控 (每 5 分鐘) |
| `ServerMonitor-Web` | `app.py` | 監控儀表板 (port 5050) |
