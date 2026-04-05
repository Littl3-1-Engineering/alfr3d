# Flask to FastAPI Migration Plan

## Overview
Convert all Flask-based services to FastAPI for improved performance, type safety, and async support.

## Current Flask Usage

### Files Using Flask (to be converted):

| File | Usage | Lines |
|------|-------|-------|
| `services/service_api/app.py` | Main REST API (Flask, Flask-CORS, Flask-SocketIO) | ~2287 |
| `services/service_api/tree_of_alfr3d.py` | Blueprint for project tree | 123 |
| `services/service_frontend/app.py` | Simple Flask server for static files + users API | 49 |

### Files Already Using Kafka-Only (no Flask):
- `service_device/app.py` - Pure Kafka consumer
- `service_user/app.py` - Pure Kafka consumer
- `service_speak/app.py` - Pure Kafka consumer
- `service_environment/` - Pure Kafka consumer

## Migration Tasks

### Priority 1: service_api/app.py

- [ ] Convert `Flask` → `FastAPI`
- [ ] Convert `flask_socketio.SocketIO` → FastAPI native WebSocket support
- [ ] Convert `flask_cors.CORS` → FastAPI `CORSMiddleware`
- [ ] Migrate all API routes (~2000+ lines)
- [ ] Update `requirements.txt`:
  - Remove: Flask, flask-cors, flask-socketio, eventlet, python-socketio
  - Add: fastapi, uvicorn, python-multipart
- [ ] Update docker-compose.yml service configuration
- [ ] Update any API documentation

### Priority 2: service_api/tree_of_alfr3d.py

- [ ] Convert Flask Blueprint → FastAPI APIRouter
- [ ] Update imports from Flask to FastAPI
- [ ] Update return types (use FastAPI Response/JSONResponse)

### Priority 3: service_frontend/app.py

- [ ] Convert Flask → FastAPI for /api/users endpoint
- [ ] Consider: Nginx already serves static files; this could become purely an API proxy
- [ ] Update imports and route decorators

### Priority 4: Test Files

- [ ] Update `tests/conftest.py` - Flask fixtures → FastAPI TestClient fixtures
- [ ] Update `tests/test_api_service.py` - Flask fixtures → FastAPI TestClient fixtures

## Technical Changes

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

### New requirements.txt for service_api:
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
python-multipart
websockets
```

## Testing

- Run existing pytest tests after migration
- Update TestClient usage from Flask to FastAPI
- Verify WebSocket functionality works with FastAPI native support

## Notes

- FastAPI's native async support will improve performance
- FastAPI auto-generates OpenAPI/Swagger documentation
- Consider migrating Kafka consumers to use async kafka client if beneficial
