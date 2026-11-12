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

# Clerk (login). Publishable key: lets us find Clerk's public keys. Secret key: reads company names.
CLERK_PUBLISHABLE_KEY = os.getenv("CLERK_PUBLISHABLE_KEY", "")
CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY", "")
# Sites allowed to use the tokens, e.g. "https://events.tmalikov.com,http://localhost:3000"
CLERK_AUTHORIZED_PARTIES = [o.strip() for o in os.getenv("CLERK_AUTHORIZED_PARTIES", "").split(",") if o.strip()]
# Protects your OpenAI bill: max AI drafts per company per day (UTC)
DAILY_DRAFT_LIMIT = int(os.getenv("DAILY_DRAFT_LIMIT", "50"))
# Gmail (Google Cloud project with Gmail API + Pub/Sub)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID", "")
GMAIL_PUBSUB_TOPIC = os.getenv("GMAIL_PUBSUB_TOPIC", "gmail-push")
GMAIL_PUSH_TOKEN = os.getenv("GMAIL_PUSH_TOKEN", "")
MAILBOX_ENCRYPTION_KEY = os.getenv("MAILBOX_ENCRYPTION_KEY", "")
APP_URL = os.getenv("APP_URL", "http://localhost:3000").rstrip("/")
# Vercel sends "Authorization: Bearer <CRON_SECRET>" to scheduled jobs
CRON_SECRET = os.getenv("CRON_SECRET", "")
# Serverless hosts run many small copies of the app, so keep each one's DB connections few
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
