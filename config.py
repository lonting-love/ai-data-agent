import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)

DB_PATH = Path(os.getenv("APP_DB_PATH") or BASE_DIR / "marketing_data.db")
CHART_DIR = Path(os.getenv("CHART_DIR") or BASE_DIR / "charts")
CHECKPOINT_DB = BASE_DIR / "checkpoint.db"
LOG_DIR = BASE_DIR / "logs"

SQL_ROW_LIMIT = int(os.getenv("SQL_ROW_LIMIT", "200"))
SQL_TIMEOUT_SECONDS = float(os.getenv("SQL_TIMEOUT_SECONDS", "5"))
MAX_QUERY_CHARS = int(os.getenv("MAX_QUERY_CHARS", "2000"))
MAX_AUTO_RESUMES = int(os.getenv("MAX_AUTO_RESUMES", "10"))

APP_API_KEY = os.getenv("APP_API_KEY", "").strip()
CHART_URL_PREFIX = "/charts"

MODEL_NAME = os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"
MODEL_BASE_URL = os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
MODEL_API_KEY = os.getenv("DEEPSEEK_API_KEY")
