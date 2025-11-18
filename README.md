# ALFR3D

A containerized microservices project for home automation, featuring Kafka messaging, MySQL database, and Python services. Includes a modern Flask web frontend with real-time dashboard monitoring and comprehensive user/device management.

## Screenshot

![ALFR3D Dashboard](screenshot.png)

## Features

- **Microservices Architecture**: Modular services for users, devices, environment, daemon, and frontend.
- **Real-Time Dashboard**: Live monitoring with CPU/memory metrics, health status, and animated connection lines.
- **Messaging**: Kafka-based communication between services with topics: `speak`, `google`, `user`, `device`, `environment`.
- **Database**: MySQL with optimized, secure queries and comprehensive schema.
- **Security**: Parameterized SQL queries to prevent injection; password hashing; secure API endpoints.
- **Performance**: Optimized DB calls with batch updates, real-time metrics collection, and efficient data fetching.
- **Modern UI**: Dark theme with professional styling, responsive design, and intuitive navigation.
- **Testing**: Comprehensive unit tests, integration tests, and API endpoint testing.
- **Containerization**: Docker Compose for local development; Kubernetes manifests for production deployment.
- **Deployment**: Full Minikube support with ingress configuration and persistent storage.

## Services

- **Zookeeper**: Required for Kafka coordination and cluster management.
- **Kafka**: Message broker with auto-created topics (`speak`, `google`, `user`, `device`, `environment`) for inter-service communication.
- **MySQL**: Database with comprehensive schema including users, devices, environments, routines, and states.
- **Service Daemon**: Core orchestration service handling voice commands, Google integration, and message routing.
- **Service User**: Manages user accounts, authentication, and online/offline status tracking.
- **Service Device**: Manages IoT devices, performs network scanning with arp-scan, and device state monitoring.
- **Service Environment**: Handles geolocation, weather updates, and environmental data collection.
- **Service API**: REST API gateway providing endpoints for users and container metrics, interfacing with database and Docker.
- **Service Frontend**: Modern React web application with real-time dashboard, user/device management, and control panel.

## Quick Start

### Local Development with Docker Compose

1. **Prerequisites**: Ensure Docker and Docker Compose are installed.
2. **Environment Setup**: Copy `.env.example` to `.env` and update environment variables (DB credentials, Kafka URLs).
3. **Database Setup**: Run the database initialization:
   ```bash
   docker-compose up mysql -d
   docker-compose exec mysql mysql -u root -p < setup/createTables.sql
   ```
4. **Start All Services**:
   ```bash
   docker-compose up --build
   ```
5. **Access the Application**:
   - Dashboard: `http://localhost:8000`
   - Real-time metrics update every 5 seconds
   - Control panel for user/device management

### Ports

- **Kafka**: 9092 (internal), 29092 (external)
- **MySQL**: 3306
- **Zookeeper**: 2181
- **Service Frontend**: 8000
- **Service API**: 5001
- **Service Daemon**: 8080
- **Service Device**: 8080
- **Service Environment**: 8080
- **Service User**: 8080

## Testing

### Running All Tests

```bash
# Install test dependencies
pip install -r tests/requirements.txt

# Run all tests
pytest tests/

# Run with coverage
pytest --cov=services/ tests/
```

### Test Categories

- **Integration Tests**: Kafka messaging between services (`test_kafka.py`)
- **Database Tests**: MySQL operations and data integrity (`test_mysql.py`)
- **Service Tests**: Individual service functionality
  - User service operations (`test_user_service.py`)
  - Device service network scanning (`test_device_service.py`)
  - Environment service data collection (`test_service_environment.py`)
- **Frontend Tests**: Dashboard API endpoints and real-time data updates

### Test Fixtures

- `kafka_bootstrap_servers`: Kafka connection configuration
- `mysql_config`: Database connection parameters
- Automatic service startup/teardown for integration tests

## Linting

Run linting across all services:

```bash
./lint.sh
```

This runs `npm run lint` for the frontend service and flake8/black for Python services. Fix issues with:

For frontend:

```bash
cd services/service_frontend && npm run lint -- --fix
```

For Python services:

```bash
black services/service_api/app.py services/service_daemon/alfr3ddaemon.py services/service_daemon/daemon.py services/service_daemon/utils/ services/service_user/app.py services/service_device/app.py services/service_environment/environment.py services/service_environment/weather_util.py
```

## Dashboard Features

The ALFR3D dashboard provides real-time monitoring and control:

### Real-Time Metrics
- **Live CPU/Memory**: Actual system resource usage for all services
- **Health Indicators**: Visual status (🟢 Healthy, 🟡 Warning, 🔴 Unhealthy)
- **Connection Lines**: Animated Kafka topic flows between services
- **Auto-Refresh**: Data updates every 5 seconds

### Management Interface
- **User Management**: Registration, editing, deletion with role-based access
- **Device Control**: Network scanning, device state monitoring
- **Environment Settings**: Location and weather data configuration
- **Routine Automation**: Scheduled task management

### Visual Design
- **Dark Theme**: Professional UI with consistent styling
- **Responsive Layout**: Works on desktop and mobile devices
- **Interactive Elements**: Hover effects and smooth animations
- **Navigation**: Unified nav bar across all pages

## Development

### Architecture Overview
- **Backend**: Flask-based microservices with Kafka messaging and REST API gateway
- **Frontend**: React application with real-time updates
- **Database**: MySQL with comprehensive schema
- **Deployment**: Docker Compose (dev) and Kubernetes (prod)

### Key Improvements
- **Real-Time Data**: Dashboard shows live metrics instead of static data
- **Security**: Parameterized SQL queries, secure API endpoints
- **Performance**: Optimized DB calls, efficient data fetching
- **UI/UX**: Modern dark theme, responsive design
- **Testing**: Comprehensive test coverage for all components
- **Deployment**: Full Kubernetes support with Minikube

### Development Workflow
1. Modify services in `services/` directories
2. Update tests in `tests/` directory
3. Run tests: `pytest tests/`
4. Lint code: `./lint.sh`
5. Rebuild: `docker-compose up --build`

### API Endpoints
- **Service API**:
  - `GET /api/users`: Retrieve online users
  - `GET /api/containers`: Retrieve container health metrics
  - `POST /api/users`: Create a new user
  - `PUT /api/users/<user_id>`: Update an existing user
  - `DELETE /api/users/<user_id>`: Delete a user
  - `GET /api/devices`: Retrieve devices
  - `POST /api/devices`: Create a new device
  - `PUT /api/devices/<device_id>`: Update an existing device
  - `DELETE /api/devices/<device_id>`: Delete a device
  - `GET /api/events`: Retrieve recent events
  - `GET /api/quips`: Retrieve quips
  - `POST /api/quips`: Create a new quip
  - `PUT /api/quips/<quip_id>`: Update an existing quip
  - `DELETE /api/quips/<quip_id>`: Delete a quip
  - `GET /api/weather`: Retrieve weather data
  - `GET /api/environment`: Retrieve environment data and override status
  - `PUT /api/environment`: Update environment data and override mode
  - `POST /api/environment/reset`: Reset to automatic detection
- **Service Frontend**:
  - `GET /`: Landing page
  - `GET /dashboard`: Real-time monitoring dashboard
  - `GET /control`: Management interface

## Kubernetes Deployment

The project includes complete Kubernetes manifests for production deployment with Minikube support.

### Prerequisites
- Minikube installed and running
- kubectl configured
- Docker for building images

### Deploy to Minikube

1. **Start Minikube**:
   ```bash
   minikube start --driver=docker
   minikube update-context
   ```

2. **Build and Load Images**:
   ```bash
   # Build all service images
   eval $(minikube docker-env)
    docker build -t alfr3d/service-frontend:latest services/service_frontend
    docker build -t alfr3d/service-api:latest services/service_api
    docker build -t alfr3d/service-daemon:latest services/service_daemon
    docker build -t alfr3d/service-device:latest services/service_device
    docker build -t alfr3d/service-environment:latest services/service_environment
    docker build -t alfr3d/service-user:latest services/service_user
   ```

3. **Deploy to Kubernetes**:
   ```bash
   kubectl apply -f k8s/
   ```

4. **Monitor Deployment**:
   ```bash
   kubectl get pods -w
   kubectl get services
   kubectl get ingress
   ```

5. **Access the Application**:
   ```bash
   # Get service URL
   minikube service service-frontend --url

   # Or configure ingress (add to /etc/hosts)
   echo "$(minikube ip) alfr3d.local" | sudo tee -a /etc/hosts
   # Then visit: http://alfr3d.local
   ```

### Kubernetes Architecture

- **StatefulSets**: Zookeeper, Kafka, MySQL with persistent storage
- **Deployments**: All ALFR3D microservices with rolling updates
- **Services**: ClusterIP for internal communication, LoadBalancer for frontend
- **ConfigMap**: Centralized environment configuration
- **Ingress**: External access with host-based routing
- **Persistent Volumes**: MySQL data persistence

### Troubleshooting

```bash
# Check pod logs
kubectl logs -f deployment/service-frontend

# Debug networking
kubectl exec -it deployment/service-frontend -- /bin/bash

# Check resource usage
kubectl top pods

# Reset deployment
kubectl delete -f k8s/
minikube delete && minikube start
```