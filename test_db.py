import pymysql

config = {
    "host": "localhost",
    "port": 3307,
    "user": "root",
    "password": "testrootpassword",
    "database": "test_alfr3d_db",
}

try:
    conn = pymysql.connect(**config)
    print("Connected to MySQL successfully")
    conn.close()
except Exception as e:
    print(f"Failed to connect: {e}")
