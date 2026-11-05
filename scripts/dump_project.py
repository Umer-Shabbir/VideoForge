import sqlite3, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage.settings_manager import get_app_data_dir

db_path = get_app_data_dir() / "videoforge.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT data_json FROM projects WHERE name LIKE '%golden_gate%'")
row = cur.fetchone()
if row:
    print(json.dumps(json.loads(row["data_json"]), indent=2))
