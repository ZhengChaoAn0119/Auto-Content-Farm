# Auto Content Farm

從 PTT 股票版每日熱門討論，透過 Gemini 與 Imagen 3 自動生成 YouTube 社群貼文內容。

## 為什麼這樣設計

兩個平台限制決定了現在的架構：

**PTT 封鎖 GCP 資料中心 IP。** PTT 會重置來自雲端業者的 TLS 連線。PTT 爬蟲必須在本地端執行，並使用 `curl_cffi` 模擬真實瀏覽器的 TLS 指紋。

**Google 封鎖來自 GCP 的無頭瀏覽器登入。** 用 Playwright 自動化 YouTube 需要真實的瀏覽器 Session。Google 能偵測並拒絕來自資料中心 IP 的登入嘗試。因此，YouTube 發文需在本地端另行處理（此功能尚未實作於本專案中）。

## 架構

```
本地端                                GCP Cloud Run
──────────────────────────────        ──────────────────────────────────────
PTT 股票版 (ptt.cc)
        │ curl_cffi（模擬 Chrome TLS）
        ▼
  local_scraper.py ── POST /run ────▶  GCS 去重複（比對已處理網址）
                      { posts }                 │
                                                ▼
                                       Gemini：摘要 + 情緒分析
                                                │
                                                ▼
                                       Gemini：貼文文字 + 圖片提示
                                                │
                                                ▼
                                       Imagen 3：9:16 圖片 → GCS
                                                │
                   ◀── { post_text, ────────────┘
                         image_blob_path,
                         processed_urls }
        │
        ▼
  output/YYYYMMDD_HHMMSS/
    ├── post_text.txt
    ├── image.png
    └── processed_urls.json
```

---

## 安裝設定

### 1. 設定 `.env`

```bash
cp .env.example .env
```

填入以下值：

```env
GEMINI_API_KEY=你的_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
GCS_BUCKET=你的_gcs_bucket_名稱
GCP_PROJECT=你的_gcp_專案_id
GOOGLE_APPLICATION_CREDENTIALS=C:\Users\你的使用者名稱\AppData\Roaming\gcloud\application_default_credentials.json
CLOUD_RUN_URL=https://你的服務網址.asia-east1.run.app

# 可選
PTT_BOARD=Stock
PTT_PUSH_THRESHOLD=30
MAX_POSTS_PER_RUN=1
```

### 2. 安裝本地端相依套件

```bash
pip install curl_cffi requests python-dotenv beautifulsoup4 google-cloud-storage
```

### 3. 登入 GCP

```bash
gcloud auth login
gcloud auth application-default login
```

---

## 部署 Cloud Run

### 首次部署

```bash
# 啟用所需 API
gcloud services enable cloudbuild.googleapis.com containerregistry.googleapis.com run.googleapis.com aiplatform.googleapis.com --project 你的專案ID

# 建置映像檔
gcloud builds submit --tag gcr.io/你的專案ID/auto-content-farm . --project 你的專案ID

# 部署
gcloud run deploy auto-content-farm \
  --image gcr.io/你的專案ID/auto-content-farm \
  --region asia-east1 \
  --memory 2Gi \
  --timeout 300 \
  --concurrency 1 \
  --allow-unauthenticated \
  --set-env-vars "GEMINI_API_KEY=...,GCS_BUCKET=...,GCP_PROJECT=...,PTT_BOARD=Stock,PTT_PUSH_THRESHOLD=30,MAX_POSTS_PER_RUN=1,GEMINI_MODEL=gemini-2.5-flash" \
  --project 你的專案ID
```

> `GOOGLE_APPLICATION_CREDENTIALS` 不需傳入 Cloud Run，Cloud Run 會自動透過附加的服務帳號進行驗證。

### 更新程式碼後重新部署

```bash
gcloud builds submit --tag gcr.io/你的專案ID/auto-content-farm . --project 你的專案ID
gcloud run deploy auto-content-farm --image gcr.io/你的專案ID/auto-content-farm --region asia-east1 --project 你的專案ID
```

---

## 執行

```bash
python local_scraper.py
```

執行後輸出範例：

```
INFO Fetching PTT index: https://www.ptt.cc/bbs/Stock/index.html
INFO Qualifying post (push=100): [閒聊] 2026/05/04 盤後閒聊
INFO Fetched 1 qualifying posts from PTT/Stock
Sending 1 post(s) to Cloud Run...
Saved to output/20260504_162135/

Post text:
今日台股...
```

Cloud Run 回傳狀態：

| 狀態 | 說明 |
|------|------|
| `ready` | 內容已生成，檔案儲存於 `output/` |
| `skipped` / `no posts above threshold` | 今日無文章達到推文門檻 |
| `skipped` / `all posts already processed` | 所有抓到的文章都已處理過 |
| HTTP 500 | 流程發生錯誤，請查看 Cloud Run 紀錄 |

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
| `GEMINI_MODEL` | 否 | `gemini-2.5-flash` | Gemini 模型 |
| `GCS_BUCKET` | 是 | — | GCS 儲存貯體（去重複與暫存圖片） |
| `GCP_PROJECT` | 是 | — | GCP 專案 ID（供 Vertex AI / Imagen 3 使用） |
| `CLOUD_RUN_URL` | 是（本地端） | — | Cloud Run 服務網址 |
| `GOOGLE_APPLICATION_CREDENTIALS` | 是（本地端） | — | ADC 憑證 JSON 路徑（僅限本地端） |
| `PTT_BOARD` | 否 | `Stock` | 要爬取的 PTT 看板 |
| `PTT_PUSH_THRESHOLD` | 否 | `30` | 最低推文數門檻 |
| `MAX_POSTS_PER_RUN` | 否 | `1` | 每次執行處理的文章數（免費 Gemini 方案建議設為 1） |

---

## 注意事項

**Gemini 429 配額超限** — 流程將每篇文章的摘要與情緒分析合併為一次 API 呼叫，並在每次呼叫之間休眠 4 秒，以符合免費方案限制（15 RPM）。若持續出現 429 錯誤，請升級為付費 Gemini API 金鑰。

**PTT 連線被重置** — `ptt.py` 會依序嘗試多種 TLS 模擬目標（`chrome124`、`safari17_0`、`chrome116`、`chrome120`）。若全部失敗，可能是 PTT 封鎖了你的 IP。

**GCS 去重複** — 已處理的 PTT 文章網址儲存於 `processed/processed_urls.json`。若需重新處理，刪除此檔案即可。
