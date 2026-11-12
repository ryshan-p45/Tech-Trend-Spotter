import os
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
