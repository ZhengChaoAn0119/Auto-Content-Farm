# Auto Content Farm

自動將 PTT 股票版每日熱門討論整理後，發佈為 YouTube 社群貼文。流程包含本地爬取 PTT、透過 GCP 進行 AI 處理，最後用 Playwright 自動發文。

## 架構

```
本地端                                   GCP Cloud Run
─────────────────────────────            ──────────────────────────────────────
PTT 股票版 (ptt.cc)
        │ curl_cffi（模擬 Chrome TLS）
        ▼
  local_scraper.py  ──── HTTPS POST /run ────▶  步驟 2：GCS 去重複
                         { posts: [...] }         │
                                                  ▼
                                             步驟 3：Gemini 摘要 + 情緒分析
                                                  │  （每篇文章 1 次 API 呼叫）
                                                  ▼
                                             步驟 4：Gemini 生成貼文文字 + 圖片提示
                                                  │
                                                  ▼
                                             步驟 5：Imagen 3 生成 9:16 圖片 → GCS
                                                  │
                                                  ▼
                                             步驟 6：Playwright 發佈 YouTube 社群貼文
                                                  │
                                                  ▼
                                             步驟 7：儲存 cookies 與已處理網址 → GCS
```

PTT 爬蟲在**本地端**執行，因為 PTT 會封鎖 GCP 資料中心的 IP。其餘步驟皆在 Cloud Run 上執行。

---

## 事前準備

- Python 3.9+（本地端）
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) 已完成登入（執行 `gcloud auth login` 與 `gcloud auth application-default login`）
- 已開啟帳單的 GCP 專案
- 已建立的 GCS 儲存貯體
- Gemini API 金鑰（正式環境建議使用付費方案；免費方案有嚴格的速率限制）
- YouTube 帳號與密碼

---

## 安裝設定

### 1. 複製專案並設定環境變數

```bash
git clone <repo>
cd auto_content_farm
cp .env.example .env
```

編輯 `.env` 填入你的設定值：

```env
# Gemini AI
GEMINI_API_KEY=你的_gemini_api_key
GEMINI_MODEL=gemini-2.0-flash

# YouTube（供 Playwright 登入使用）
YT_EMAIL=你的_youtube_email@gmail.com
YT_PASSWORD=你的_youtube_密碼

# Google Cloud Storage
GCS_BUCKET=你的_gcs_bucket_名稱
GOOGLE_APPLICATION_CREDENTIALS=C:\Users\你的使用者名稱\AppData\Roaming\gcloud\application_default_credentials.json

# Cloud Run 端點（部署完成後填入）
CLOUD_RUN_URL=https://你的-cloud-run-網址.run.app

# 爬蟲參數（可選）
PTT_BOARD=Stock
PTT_PUSH_THRESHOLD=30   # 最低推文數門檻
MAX_POSTS_PER_RUN=1     # 使用免費 Gemini 方案時建議設為 1，避免 429 錯誤
```

### 2. 安裝本地端相依套件

本地端只需安裝少量套件，不需要完整的 Cloud Run 環境：

```bash
pip install curl_cffi requests python-dotenv beautifulsoup4
```

---

## 首次 GCP 部署

以下步驟只需執行一次。之後更新程式碼只需重新執行步驟 3～4。

### 1. 啟用所需 API

```bash
gcloud services enable cloudbuild.googleapis.com containerregistry.googleapis.com run.googleapis.com --project 你的專案ID
```

### 2. 使用 Cloud Build 建置 Docker 映像檔

```bash
gcloud builds submit --tag gcr.io/你的專案ID/auto-content-farm . --project 你的專案ID
```

### 3. 部署至 Cloud Run

```bash
gcloud run deploy auto-content-farm \
  --image gcr.io/你的專案ID/auto-content-farm \
  --region asia-east1 \
  --platform managed \
  --memory 2Gi \
  --timeout 300 \
  --concurrency 1 \
  --service-account 你的專案編號-compute@developer.gserviceaccount.com \
  --allow-unauthenticated \
  --set-env-vars "GEMINI_API_KEY=...,GCS_BUCKET=...,YT_EMAIL=...,YT_PASSWORD=...,PTT_BOARD=Stock,PTT_PUSH_THRESHOLD=30,MAX_POSTS_PER_RUN=1,GEMINI_MODEL=gemini-2.0-flash" \
  --project 你的專案ID
```

> `GOOGLE_APPLICATION_CREDENTIALS` **不需要**傳入 Cloud Run，Cloud Run 會自動透過附加的服務帳號進行身份驗證。

### 4. 將 Service URL 填回 .env

部署完成後，終端機會顯示類似以下的網址：

```
Service URL: https://auto-content-farm-XXXXXXXXXX.asia-east1.run.app
```

將它填入 `.env`：

```env
CLOUD_RUN_URL=https://auto-content-farm-XXXXXXXXXX.asia-east1.run.app
```

---

## 執行流程

```bash
python local_scraper.py
```

執行後輸出範例：

```
2026-05-04 09:00:01 INFO Fetching PTT index: https://www.ptt.cc/bbs/Stock/index.html
2026-05-04 09:00:02 INFO Qualifying post (push=100): [爆卦] ...
2026-05-04 09:00:02 INFO Fetched 1 qualifying posts from PTT/Stock
Sending 1 post(s) to Cloud Run...
{'status': 'success', 'posts_processed': 1}
```

Cloud Run 可能回傳的結果：

| 回傳結果 | 說明 |
|---------|------|
| `{"status": "success", "posts_processed": N}` | 成功發佈 N 篇 YouTube 社群貼文 |
| `{"status": "skipped", "reason": "no posts above threshold"}` | 今日無文章達到推文門檻 |
| `{"status": "skipped", "reason": "all posts already processed"}` | 所有抓到的文章都已發佈過 |
| HTTP 500 | 流程發生錯誤，請查看 Cloud Run 紀錄 |

---

## 更新程式碼後重新部署

```bash
gcloud builds submit --tag gcr.io/你的專案ID/auto-content-farm . --project 你的專案ID
gcloud run deploy auto-content-farm --image gcr.io/你的專案ID/auto-content-farm --region asia-east1 --project 你的專案ID
```

---

## 查看 Cloud Run 紀錄

```bash
gcloud run services logs read auto-content-farm --region=asia-east1 --limit=50 --project 你的專案ID
```

---

## 環境變數說明

| 變數名稱 | 必填 | 預設值 | 說明 |
|---------|------|--------|------|
| `GEMINI_API_KEY` | 是 | — | Gemini API 金鑰 |
| `GEMINI_MODEL` | 否 | `gemini-2.0-flash` | 使用的 Gemini 模型 |
| `YT_EMAIL` | 是 | — | YouTube 帳號 Email |
| `YT_PASSWORD` | 是 | — | YouTube 帳號密碼 |
| `GCS_BUCKET` | 是 | — | GCS 儲存貯體名稱 |
| `CLOUD_RUN_URL` | 是（本地端） | — | Cloud Run 服務網址 |
| `GOOGLE_APPLICATION_CREDENTIALS` | 是（本地端） | — | ADC 憑證 JSON 路徑（僅限本地端） |
| `PTT_BOARD` | 否 | `Stock` | 要爬取的 PTT 看板 |
| `PTT_PUSH_THRESHOLD` | 否 | `30` | 文章最低推文數門檻 |
| `MAX_POSTS_PER_RUN` | 否 | `1` | 每次執行最多處理的文章數 |

---

## GCS 狀態檔案說明

流程執行時會在 GCS 儲存貯體中維護以下狀態檔案：

| 路徑 | 內容 |
|------|------|
| `processed/processed_urls.json` | 已發佈文章的網址清單（用於去重複） |
| `cookies/youtube_cookies.json` | YouTube 登入 Session Cookie（跨次執行重複使用） |
| `images/temp_*.png` | 暫存的 AI 生成圖片（發文後自動刪除） |

---

## Gemini API 配額說明

流程將每篇文章的摘要與情緒分析**合併為一次 Gemini API 呼叫**，並在每次呼叫之間加入 4 秒間隔，以符合免費方案的速率限制（15 RPM）。使用 `MAX_POSTS_PER_RUN=1` 時，每次執行共呼叫 3 次 API（摘要+情緒、生成貼文文字、生成圖片提示）。

若仍持續出現 429 錯誤，請至 https://ai.google.dev 將 API 金鑰升級為付費方案。

---

## 常見問題

**Gemini 回傳 429 配額超限**
等待一分鐘後重試。若持續發生，請升級為付費 API 金鑰，或調低 `PTT_PUSH_THRESHOLD` 以減少符合條件的文章數。

**PTT 連線被重置**
`ptt.py` 使用 `curl_cffi` 模擬 Chrome 的 TLS 指紋來繞過封鎖。若仍出現連線錯誤，請確認本地端已安裝 `curl_cffi`（`pip install curl_cffi`）。

**YouTube 登入失敗**
GCS 中儲存的 Session Cookie 可能已過期。刪除儲存貯體中的 `cookies/youtube_cookies.json` 後，下次執行時會重新登入。

**Cloud Run `/run` 回傳 500**
使用上方的指令查看紀錄，常見原因包括：Gemini 配額超限、Imagen 3 安全過濾器拒絕圖片，或 Playwright 在發佈 YouTube 貼文時逾時。
