# Auto Content Farm

Generates daily YouTube Community Post content from hot PTT Stock board discussions using Gemini and Imagen 3.

## Why it's structured this way

Two platform restrictions shaped the architecture:

**PTT blocks GCP datacenter IPs.** PTT resets TLS connections from cloud providers. PTT scraping must run locally using `curl_cffi` to impersonate a real browser's TLS fingerprint.

**Google blocks headless browser login from GCP.** Automating YouTube via Playwright requires a real browser session. Google detects and rejects login attempts from datacenter IPs. YouTube posting is therefore handled separately as a local step (not yet implemented in this repo).

## Architecture

```
Local machine                         GCP Cloud Run
──────────────────────────────        ──────────────────────────────────────
PTT Stock board (ptt.cc)
        │ curl_cffi (Chrome TLS)
        ▼
  local_scraper.py ── POST /run ────▶  Dedup against GCS processed URLs
                      { posts }                 │
                                                ▼
                                       Gemini: summarize + sentiment
                                                │
                                                ▼
                                       Gemini: post text + image prompt
                                                │
                                                ▼
                                       Imagen 3: 9:16 image → GCS
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

## Setup

### 1. Configure `.env`

```bash
cp .env.example .env
```

Fill in:

```env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
GCS_BUCKET=your_gcs_bucket_name
GCP_PROJECT=your_gcp_project_id
GOOGLE_APPLICATION_CREDENTIALS=C:\Users\you\AppData\Roaming\gcloud\application_default_credentials.json
CLOUD_RUN_URL=https://your-service-url.asia-east1.run.app

# Optional
PTT_BOARD=Stock
PTT_PUSH_THRESHOLD=30
MAX_POSTS_PER_RUN=1
```

### 2. Install local dependencies

```bash
pip install curl_cffi requests python-dotenv beautifulsoup4 google-cloud-storage
```

### 3. Authenticate with GCP

```bash
gcloud auth login
gcloud auth application-default login
```

---

## Deploy Cloud Run

### First time

```bash
# Enable APIs
gcloud services enable cloudbuild.googleapis.com containerregistry.googleapis.com run.googleapis.com aiplatform.googleapis.com --project YOUR_PROJECT_ID

# Build
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/auto-content-farm . --project YOUR_PROJECT_ID

# Deploy
gcloud run deploy auto-content-farm \
  --image gcr.io/YOUR_PROJECT_ID/auto-content-farm \
  --region asia-east1 \
  --memory 2Gi \
  --timeout 300 \
  --concurrency 1 \
  --allow-unauthenticated \
  --set-env-vars "GEMINI_API_KEY=...,GCS_BUCKET=...,GCP_PROJECT=...,PTT_BOARD=Stock,PTT_PUSH_THRESHOLD=30,MAX_POSTS_PER_RUN=1,GEMINI_MODEL=gemini-2.5-flash" \
  --project YOUR_PROJECT_ID
```

> `GOOGLE_APPLICATION_CREDENTIALS` is not passed to Cloud Run — it uses the attached service account automatically.

### Redeploy after changes

```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/auto-content-farm . --project YOUR_PROJECT_ID
gcloud run deploy auto-content-farm --image gcr.io/YOUR_PROJECT_ID/auto-content-farm --region asia-east1 --project YOUR_PROJECT_ID
```

---

## Run

```bash
python local_scraper.py
```

Sample output:

```
INFO Fetching PTT index: https://www.ptt.cc/bbs/Stock/index.html
INFO Qualifying post (push=100): [閒聊] 2026/05/04 盤後閒聊
INFO Fetched 1 qualifying posts from PTT/Stock
Sending 1 post(s) to Cloud Run...
Saved to output/20260504_162135/

Post text:
今日台股...
```

Cloud Run responses:

| Status | Meaning |
|--------|---------|
| `ready` | Content generated — files saved to `output/` |
| `skipped` / `no posts above threshold` | No PTT posts met the push threshold |
| `skipped` / `all posts already processed` | All fetched posts were already processed |
| HTTP 500 | Pipeline error — check logs |

---

## Check logs

```bash
gcloud run services logs read auto-content-farm --region=asia-east1 --limit=50 --project YOUR_PROJECT_ID
```

---

## Configuration reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | Yes | — | Gemini API key |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Gemini model |
| `GCS_BUCKET` | Yes | — | GCS bucket for dedup and temp images |
| `GCP_PROJECT` | Yes | — | GCP project ID (for Vertex AI / Imagen 3) |
| `CLOUD_RUN_URL` | Yes (local) | — | Cloud Run service URL |
| `GOOGLE_APPLICATION_CREDENTIALS` | Yes (local) | — | ADC JSON path (local only) |
| `PTT_BOARD` | No | `Stock` | PTT board to crawl |
| `PTT_PUSH_THRESHOLD` | No | `30` | Minimum push count |
| `MAX_POSTS_PER_RUN` | No | `1` | Posts per run (keep at 1 on free Gemini tier) |

---

## Notes

**Gemini 429 errors** — The pipeline batches summarize + sentiment into one call per post and sleeps 4 seconds between calls to stay under the free-tier limit (15 RPM). If 429s persist, upgrade to a paid Gemini API key.

**PTT connection reset** — `ptt.py` tries multiple TLS impersonation targets (`chrome124`, `safari17_0`, `chrome116`, `chrome120`) in order. If all fail, PTT may be blocking your IP.

**GCS dedup** — Processed PTT URLs are saved in `processed/processed_urls.json`. Delete this file to reprocess posts.
