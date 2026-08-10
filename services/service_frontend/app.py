"""Frontend service for ALFR3D, serving the web dashboard and API endpoints."""

import sys
import os
import logging
import pymysql
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from common import get_connection

logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/users")
async def get_users() -> List[Dict[str, str]]:
    db = get_connection()
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
        return user_list
    except pymysql.Error as e:
        logger.error(f"Database error getting users: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        db.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
