# Auto Content Farm

Automatically publishes daily YouTube Community Posts summarizing hot PTT Stock board discussions. The pipeline scrapes PTT locally, routes content through GCP for AI processing, and publishes via Playwright.

## Architecture

```
Local machine                          GCP Cloud Run
─────────────────────────────          ──────────────────────────────────────
PTT Stock board (ptt.cc)
        │ curl_cffi (Chrome TLS)
        ▼
  local_scraper.py  ──── HTTPS POST /run ────▶  Step 2: GCS dedup
                         { posts: [...] }         │
                                                  ▼
                                             Step 3: Gemini summarize + sentiment
                                                  │  (1 API call per post)
                                                  ▼
                                             Step 4: Gemini → post text + image prompt
                                                  │
                                                  ▼
                                             Step 5: Imagen 3 → 9:16 image → GCS
                                                  │
                                                  ▼
                                             Step 6: Playwright → YouTube Community Post
                                                  │
                                                  ▼
                                             Step 7: Save cookies + processed URLs → GCS
```

PTT scraping runs **locally** because PTT blocks GCP datacenter IPs. Everything else runs on Cloud Run.

---

## Prerequisites

- Python 3.9+ (local)
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) authenticated (`gcloud auth login` + `gcloud auth application-default login`)
- A GCP project with billing enabled
- GCS bucket created
- Gemini API key (paid tier recommended; free tier has strict rate limits)
- YouTube account credentials

---

## Setup

### 1. Clone and configure

```bash
git clone <repo>
cd auto_content_farm
cp .env.example .env
```

Edit `.env` with your values:

```env
# Gemini AI
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash

# YouTube (for Playwright login)
YT_EMAIL=your_youtube_email@gmail.com
YT_PASSWORD=your_youtube_password_here

# Google Cloud Storage
GCS_BUCKET=your_gcs_bucket_name_here
GOOGLE_APPLICATION_CREDENTIALS=C:\Users\you\AppData\Roaming\gcloud\application_default_credentials.json

# Cloud Run endpoint (set after deployment)
CLOUD_RUN_URL=https://your-cloud-run-url.run.app

# Pipeline tuning (optional)
PTT_BOARD=Stock
PTT_PUSH_THRESHOLD=30   # minimum push count to include a post
MAX_POSTS_PER_RUN=1     # keep at 1 on free Gemini tier to avoid 429 errors
```

### 2. Install local dependencies

Only a small set of packages is needed to run the scraper locally:

```bash
pip install curl_cffi requests python-dotenv beautifulsoup4
```

---

## First-time GCP deployment

Run these once. After that, re-deployment only needs steps 3–4.

### 1. Enable required APIs

```bash
gcloud services enable cloudbuild.googleapis.com containerregistry.googleapis.com run.googleapis.com --project YOUR_PROJECT_ID
```

### 2. Build the Docker image on Cloud Build

```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/auto-content-farm . --project YOUR_PROJECT_ID
```

### 3. Deploy to Cloud Run

```bash
gcloud run deploy auto-content-farm \
  --image gcr.io/YOUR_PROJECT_ID/auto-content-farm \
  --region asia-east1 \
  --platform managed \
  --memory 2Gi \
  --timeout 300 \
  --concurrency 1 \
  --service-account YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com \
  --allow-unauthenticated \
  --set-env-vars "GEMINI_API_KEY=...,GCS_BUCKET=...,YT_EMAIL=...,YT_PASSWORD=...,PTT_BOARD=Stock,PTT_PUSH_THRESHOLD=30,MAX_POSTS_PER_RUN=1,GEMINI_MODEL=gemini-2.0-flash" \
  --project YOUR_PROJECT_ID
```

> `GOOGLE_APPLICATION_CREDENTIALS` is **not** passed to Cloud Run — it authenticates automatically via the attached service account.

### 4. Copy the Service URL into .env

After the deploy command completes, it prints a Service URL like:

```
Service URL: https://auto-content-farm-XXXXXXXXXX.asia-east1.run.app
```

Add it to your `.env`:

```env
CLOUD_RUN_URL=https://auto-content-farm-XXXXXXXXXX.asia-east1.run.app
```

---

## Running the pipeline

```bash
python local_scraper.py
```

Sample output:

```
2026-05-04 09:00:01 INFO Fetching PTT index: https://www.ptt.cc/bbs/Stock/index.html
2026-05-04 09:00:02 INFO Qualifying post (push=100): [爆卦] ...
2026-05-04 09:00:02 INFO Fetched 1 qualifying posts from PTT/Stock
Sending 1 post(s) to Cloud Run...
{'status': 'success', 'posts_processed': 1}
```

Possible responses from Cloud Run:

| Response | Meaning |
|----------|---------|
| `{"status": "success", "posts_processed": N}` | N posts published to YouTube |
| `{"status": "skipped", "reason": "no posts above threshold"}` | No posts met the push threshold today |
| `{"status": "skipped", "reason": "all posts already processed"}` | All fetched posts were already published |
| HTTP 500 | Pipeline error — check logs (see below) |

---

## Redeployment (after code changes)

```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/auto-content-farm . --project YOUR_PROJECT_ID
gcloud run deploy auto-content-farm --image gcr.io/YOUR_PROJECT_ID/auto-content-farm --region asia-east1 --project YOUR_PROJECT_ID
```

---

## Checking Cloud Run logs

```bash
gcloud run services logs read auto-content-farm --region=asia-east1 --limit=50 --project YOUR_PROJECT_ID
```

---

## Configuration reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | Yes | — | Gemini API key |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Gemini model name |
| `YT_EMAIL` | Yes | — | YouTube account email |
| `YT_PASSWORD` | Yes | — | YouTube account password |
| `GCS_BUCKET` | Yes | — | GCS bucket name for state |
| `CLOUD_RUN_URL` | Yes (local) | — | Cloud Run service URL |
| `GOOGLE_APPLICATION_CREDENTIALS` | Yes (local) | — | Path to ADC JSON (local only) |
| `PTT_BOARD` | No | `Stock` | PTT board to crawl |
| `PTT_PUSH_THRESHOLD` | No | `30` | Minimum push count to qualify |
| `MAX_POSTS_PER_RUN` | No | `1` | Posts to process per run |

---

## GCS state files

The pipeline stores state in your GCS bucket:

| Path | Contents |
|------|---------|
| `processed/processed_urls.json` | URLs already published (dedup list) |
| `cookies/youtube_cookies.json` | YouTube session cookies (reused across runs) |
| `images/temp_*.png` | Temporary generated images (deleted after posting) |

---

## Gemini API quota

The pipeline batches summarize + sentiment into **one Gemini call per post** and adds a 4-second sleep between each API call to stay within the free-tier limit (15 RPM). With `MAX_POSTS_PER_RUN=1`, the total per-run call count is 3 (summarize+sentiment, generate_post_text, generate_image_prompt).

If you still see 429 errors, upgrade your Gemini API key to a paid plan at https://ai.google.dev.

---

## Troubleshooting

**Gemini 429 quota exceeded**
Wait a minute and retry. If it recurs, upgrade to a paid API key or lower `PTT_PUSH_THRESHOLD` to reduce the chance of qualifying posts.

**PTT connection reset**
`ptt.py` uses `curl_cffi` to impersonate Chrome's TLS fingerprint. If you see connection errors, ensure `curl_cffi` is installed locally (`pip install curl_cffi`).

**YouTube login fails**
Session cookies in GCS may be stale. Delete `cookies/youtube_cookies.json` from the bucket to force a fresh login on the next run.

**Cloud Run 500 on `/run`**
Check logs with the command above. Common causes: Gemini quota, Imagen 3 safety filter rejection, or Playwright timeout during YouTube posting.
