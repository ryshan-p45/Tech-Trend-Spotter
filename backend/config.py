import os
from pathlib import Path
from dotenv import load_dotenv

"""
Central place for reading configuration from environment variables.
Values come from a local .env file in development and from Railway's
service variables in production. Secrets must never be hardcoded here.
"""


# Load backend/.env if it exists (no-op in production where it is absent)
load_dotenv()

# Full Postgres connection string, e.g. postgresql://user:pass@localhost:5432/techtrendspotter
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Comma-separated list of frontend origins allowed to call the API
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

# User-Agent sent by data collectors so site owners can identify our traffic.
# Keep it generic - do not put personal emails or names in here.
COLLECTOR_USER_AGENT = os.getenv("COLLECTOR_USER_AGENT", "TechTrendSpotterBot/0.1")

# Per-request timeout (seconds) for data collectors talking to external sources
COLLECTOR_TIMEOUT_SECONDS = float(os.getenv("COLLECTOR_TIMEOUT_SECONDS", "10"))

# Path to the YAML file listing data collection sources. Defaults to the file
# shipped next to the collectors; override to use a different set per environment.
SOURCES_CONFIG_PATH = Path(os.getenv(
    "SOURCES_CONFIG_PATH",
    str(Path(__file__).parent / "functionality" / "data_collection" / "sources.yaml"),
))
