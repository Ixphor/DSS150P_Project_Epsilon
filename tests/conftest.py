import os
import sys
from pathlib import Path

# Allow `import src...` when pytest runs from the repo root, and satisfy db.py's password check.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("POSTGRES_PASSWORD", "test-only")
