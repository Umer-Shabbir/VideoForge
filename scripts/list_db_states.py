import sqlite3
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage.settings_manager import get_app_data_dir

db_path = get_app_data_dir() / "videoforge.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT p.id, p.name, p.status, p.data_json, j.job_id, j.state, j.data_json as j_data FROM projects p LEFT JOIN jobs j ON p.id = j.project_id")
for r in cur.fetchall():
    print(f"{r['name'][:45]:<45} | P: {r['status']:<10} | J: {str(r['state']):<10}")
