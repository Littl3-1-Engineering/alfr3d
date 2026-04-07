docker build -t alfr3d/service-frontend:latest -f services/service_frontend/Dockerfile services/service_frontend
docker build -t alfr3d/service-api:latest -f services/service_api/Dockerfile services
docker build -t alfr3d/service-daemon:latest -f services/service_daemon/Dockerfile services
docker build -t alfr3d/service-device:latest -f services/service_device/Dockerfile services
docker build -t alfr3d/service-environment:latest -f services/service_environment/Dockerfile services
docker build -t alfr3d/service-user:latest -f services/service_user/Dockerfile services
docker build -t alfr3d/service-speak:latest -f services/service_speak/Dockerfile services
