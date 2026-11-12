import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Some Anaconda installs set SSL_CERT_FILE to a file that doesn't exist,
# which breaks every HTTPS call. Ignore it if the file is missing.
if os.getenv("SSL_CERT_FILE") and not os.path.exists(os.environ["SSL_CERT_FILE"]):
    del os.environ["SSL_CERT_FILE"]

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://inbox:inbox@localhost:5433/inbox")
# Hosted Postgres (Neon on Vercel) hands out "postgres://" or "postgresql://"; SQLAlchemy needs the driver name
DATABASE_URL = re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", DATABASE_URL)
# LangGraph's checkpointer uses plain psycopg, which wants "postgresql://" without the driver suffix
CHECKPOINT_URL = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4.1-mini")
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536

OWNER_PASSWORD = os.getenv("OWNER_PASSWORD", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
SESSION_DAYS = 30
# Serverless hosts run many small copies of the app, so keep each one's DB connections few
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
