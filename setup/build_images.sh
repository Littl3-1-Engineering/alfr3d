#!/bin/bash
export DOCKER_BUILDKIT=1

docker build -t alfr3d/service-frontend:v0.1.5 -f services/service_frontend/Dockerfile services/service_frontend
docker build -t alfr3d/service-api:v0.1.5 -f services/service_api/Dockerfile services
docker build -t alfr3d/service-daemon:v0.1.5 -f services/service_daemon/Dockerfile services
docker build -t alfr3d/service-device:v0.1.5 -f services/service_device/Dockerfile services
docker build -t alfr3d/service-environment:v0.1.5 -f services/service_environment/Dockerfile services
docker build -t alfr3d/service-user:v0.1.5 -f services/service_user/Dockerfile services
docker build -t alfr3d/service-speak:v0.1.5 -f services/service_speak/Dockerfile services
