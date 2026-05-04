import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from config import get_config
import pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Auto Content Farm")


class RunRequest(BaseModel):
    posts: list[dict] | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run")
def run(req: RunRequest = RunRequest()):
    try:
        cfg = get_config()
        result = pipeline.run(cfg, posts=req.posts)
        logger.info("Pipeline result: %s", result)
        return result
    except Exception as e:
        logger.exception("Pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))
