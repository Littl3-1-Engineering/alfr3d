"""Frontend service for ALFR3D, serving the web dashboard and API endpoints."""

from flask import Flask, jsonify
import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder="dist", static_url_path="")

MYSQL_DATABASE = os.environ["MYSQL_DATABASE"]
MYSQL_USER = os.environ["MYSQL_USER"]
MYSQL_PSWD = os.environ["MYSQL_PSWD"]
MYSQL_DB = os.environ["MYSQL_NAME"]


@app.route("/api/users")
def get_users():
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
        )
        cursor = db.cursor()
        # Get online users, join with user_types to get type name
        cursor.execute(
            """
            SELECT u.username, ut.type
            FROM user u
            JOIN user_types ut ON u.type = ut.id
            JOIN states s ON u.state = s.id
            WHERE s.state = 'online' AND ut.type IN ('resident', 'guest')
        """
        )
        users = cursor.fetchall()
        db.close()
        # Format as list of dicts
        user_list = [{"name": user[0], "type": user[1]} for user in users]
        return jsonify(user_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
