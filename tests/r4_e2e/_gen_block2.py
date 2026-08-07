import sqlite3
import tempfile
import shutil

prod_db = r"d:\IT-department\SOP_PROD\05_UI_Demo\db\it_asset_platform.sqlite"
with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
    tmp_db = tmp.name

shutil.copy(prod_db, tmp_db)
conn = sqlite3.connect(tmp_db)
cursor = conn.cursor()
cursor.execute("UPDATE assets SET status='x' WHERE id=1")
conn.commit()
conn.close()
