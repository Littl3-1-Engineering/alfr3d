"""Frontend service for ALFR3D, serving the web dashboard and API endpoints."""

from flask import Flask, jsonify
import os
import logging
import pymysql
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder="dist", static_url_path="")

logger = logging.getLogger(__name__)

MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "mysql")
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD", "")
MYSQL_DB = os.environ.get("MYSQL_NAME", "alfr3d_db")


@app.route("/api/users")
def get_users():
    db = pymysql.connect(
        host=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PSWD, database=MYSQL_DB
    )
    cursor = db.cursor()
    try:
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
        user_list = [{"name": user[0], "type": user[1]} for user in users]
        return jsonify(user_list)
    except pymysql.Error as e:
        logger.error(f"Database error getting users: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        db.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
