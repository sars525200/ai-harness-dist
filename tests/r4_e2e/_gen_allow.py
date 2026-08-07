import sqlite3

db_path = r'd:\IT-department\SOP_PROD\05_UI_Demo\db\it_asset_platform.sqlite'

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('SELECT id, status FROM assets LIMIT 5')
    results = cursor.fetchall()

    print("Query Results:")
    for row in results:
        print(row)

    conn.close()
except Exception as e:
    print(f"Error: {e}")
