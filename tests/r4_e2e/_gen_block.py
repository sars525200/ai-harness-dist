import sqlite3

db_path = r'd:\IT-department\SOP_PROD\05_UI_Demo\db\it_asset_platform.sqlite'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("UPDATE assets SET status='x' WHERE id=1")
conn.commit()

conn.close()
