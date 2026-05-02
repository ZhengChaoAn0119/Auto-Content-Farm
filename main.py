import logging
from fastapi import FastAPI, HTTPException
from config import get_config
import pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Auto Content Farm")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run")
def run():
    try:
        cfg = get_config()
        result = pipeline.run(cfg)
        logger.info("Pipeline result: %s", result)
        return result
    except Exception as e:
        logger.exception("Pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))
