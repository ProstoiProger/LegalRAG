import os
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

PORT = int(os.getenv("PORT", "8000"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")

QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")

ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "")

ES_INDEX = os.getenv("ES_INDEX", "bm25")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "dense_structured_bge_m3_v1")
ALPHA = float(os.getenv("ALPHA", "0.4"))
