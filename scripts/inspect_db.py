import sqlite3, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage.settings_manager import get_app_data_dir

db_path = get_app_data_dir() / "videoforge.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT id, name, status, data_json FROM projects")
rows = cur.fetchall()
print(f"Total projects in APPDATA videoforge.db: {len(rows)}")
for r in rows:
    data = json.loads(r["data_json"])
    prof = data.get("profile", {})
    print(f"{r['name'][:40]:<40} | preset_name: {data.get('preset_name')} | font: {prof.get('subtitle_font')} | size: {prof.get('subtitle_font_size')} | pri: {prof.get('subtitle_primary_color')} | kar: {prof.get('subtitle_karaoke_color')}")
