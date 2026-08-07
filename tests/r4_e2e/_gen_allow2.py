import sqlite3

db_path = r"d:\IT-department\SOP_PROD\05_UI_Demo\db\it_asset_platform.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT id, status FROM assets LIMIT 5")
results = cursor.fetchall()

print("id, status")
for row in results:
    print(row)

conn.close()
