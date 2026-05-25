import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def build_database_path() -> Path:
    raw_path = os.getenv("DATABASE_PATH", "").strip()

    if not raw_path:
        return BASE_DIR / "antifake.db"

    path = Path(raw_path)

    if path.is_absolute():
        return path

    return BASE_DIR / path


DATABASE_PATH = build_database_path()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini").strip()

CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
GITHUB_URL = os.getenv("GITHUB_URL", "").strip()
METHODOLOGY_URL = os.getenv("METHODOLOGY_URL", "").strip()

LIQPAY_PUBLIC_KEY = os.getenv("LIQPAY_PUBLIC_KEY", "").strip()
LIQPAY_PRIVATE_KEY = os.getenv("LIQPAY_PRIVATE_KEY", "").strip()
LIQPAY_SANDBOX = os.getenv("LIQPAY_SANDBOX", "1").strip() == "1"
BASE_WEBHOOK_URL = os.getenv("BASE_WEBHOOK_URL", "").strip().rstrip("/")
PAYMENT_RESULT_URL = os.getenv("PAYMENT_RESULT_URL", "").strip()
SUPPORT_JAR_URL = os.getenv("SUPPORT_JAR_URL", "https://send.monobank.ua/jar/AgE5cQTo4P").strip()


def parse_admin_ids(value: str) -> set[int]:
    admin_ids = set()

    for item in value.split(","):
        item = item.strip()

        if item.isdigit():
            admin_ids.add(int(item))

    return admin_ids


def parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


ADMIN_IDS = parse_admin_ids(os.getenv("ADMIN_IDS", ""))
FREE_TEXT_LIMIT = parse_int(os.getenv("FREE_TEXT_LIMIT"), 30)
