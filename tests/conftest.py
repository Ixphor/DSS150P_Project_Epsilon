import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")                                  # real password first
os.environ.setdefault("POSTGRES_PASSWORD", "test-only")     # fallback for machines with no .env