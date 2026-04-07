# Flask to FastAPI Migration Plan

## Status: ✅ COMPLETE

All Flask-based services have been converted to FastAPI.

---

## Overview
Convert all Flask-based services to FastAPI for improved performance, type safety, and async support.

## Current FastAPI Usage (All Migrated ✓)

### Files Using FastAPI (converted from Flask):

| File | Usage | Lines |
|------|-------|-------|
| `services/service_api/app.py` | Main REST API (FastAPI, WebSocket) | ~2100 |
| `services/service_api/tree_of_alfr3d.py` | APIRouter for project tree | 130 |
| `services/service_frontend/app.py` | FastAPI server for static files + users API | 58 |

### Files Already Using Kafka-Only (no Flask):
- `service_device/app.py` - Pure Kafka consumer
- `service_user/app.py` - Pure Kafka consumer
- `service_speak/app.py` - Pure Kafka consumer
- `service_environment/` - Pure Kafka consumer

## Migration Tasks

### Priority 1: service_api/app.py

- [x] Convert `Flask` → `FastAPI`
- [x] Convert `flask_socketio.SocketIO` → FastAPI native WebSocket support
- [x] Convert `flask_cors.CORS` → FastAPI `CORSMiddleware`
- [x] Migrate all API routes (~2000+ lines)
- [x] Update `requirements.txt`:
  - Remove: Flask, flask-cors, flask-socketio, eventlet, python-socketio
  - Add: fastapi, uvicorn, python-multipart
- [x] Update docker-compose.yml service configuration
- [x] Update any API documentation

### Priority 2: service_api/tree_of_alfr3d.py

- [x] Convert Flask Blueprint → FastAPI APIRouter
- [x] Update imports from Flask to FastAPI
- [x] Update return types (use FastAPI Response/JSONResponse)

### Priority 3: service_frontend/app.py

- [x] Convert Flask → FastAPI for /api/users endpoint
- [x] Consider: Nginx already serves static files; this could become purely an API proxy
- [x] Update imports and route decorators

### Priority 4: Test Files

- [x] Update `tests/conftest.py` - Flask fixtures → FastAPI TestClient fixtures
- [x] Update `tests/test_api_service.py` - Flask fixtures → FastAPI TestClient fixtures

## Implementation Notes

### Before (Flask):
```python
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route("/api/devices", methods=["GET"])
def get_devices():
    return jsonify(devices)
```

### After (FastAPI):
```python
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi import WebSocket
from fastapi.responses import JSONResponse

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"])

@app.get("/api/devices")
async def get_devices():
    return devices

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # handle websocket
```

## Dependencies

### Current requirements.txt for service_api:
```
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
pymysql==1.1.2
DBUtils==3.1.0
kafka-python-ng==2.2.3
docker==7.0.0
cryptography==46.0.5
requests==2.32.4
orjson
pydantic>=2.0.0
websockets
```

## Testing

- [x] Run existing pytest tests after migration
- [x] Update TestClient usage from Flask to FastAPI
- [x] Verify WebSocket functionality works with FastAPI native support

## Notes

- FastAPI's native async support improved performance
- FastAPI auto-generates OpenAPI/Swagger documentation
- Kafka consumers remain synchronous (kafka-python-ng)
- Migration completed successfully
