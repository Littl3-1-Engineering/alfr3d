#!/bin/bash

# Linting script for Alfr3d project

echo "Running linting on all services..."

# Frontend (Node.js)
echo "Linting service_frontend..."
# Run npm lint to check for JavaScript/React code style and potential errors
cd services/service_frontend || exit 1
npm run lint || exit 1

# API service
echo "Linting service_api..."
# Use flake8 to check for Python style violations in app.py, with max line length 100 and ignoring E203,W503
# Use black to check if app.py is properly formatted
cd ../service_api || exit 1
flake8 app.py --max-line-length=100 --ignore=E203,W503 || exit 1
black --check --diff --line-length=100 app.py || exit 1

# Daemon service
echo "Linting service_daemon..."
# Use flake8 to check for Python style violations in alfr3ddaemon.py, daemon.py, and utils/ directory, with max line length 100 and ignoring E203,W503
# Use black to check if the specified files are properly formatted
cd ../service_daemon || exit 1
flake8 alfr3ddaemon.py daemon.py utils/ --max-line-length=100 --ignore=E203,W503 || exit 1
black --check --diff --line-length=100 alfr3ddaemon.py daemon.py utils/ || exit 1

# User service
echo "Linting service_user..."
# Use flake8 to check for Python style violations in app.py, with max line length 100 and ignoring E203,W503
# Use black to check if app.py is properly formatted
cd ../service_user || exit 1
flake8 app.py --max-line-length=100 --ignore=E203,W503 || exit 1
black --check --diff --line-length=100 app.py || exit 1

# Device service
echo "Linting service_device..."
# Use flake8 to check for Python style violations in app.py, with max line length 100 and ignoring E203,W503
# Use black to check if app.py is properly formatted
cd ../service_device || exit 1
flake8 app.py --max-line-length=100 --ignore=E203,W503 || exit 1
black --check --diff --line-length=100 app.py || exit 1

# Environment service
echo "Linting service_environment..."
# Use flake8 to check for Python style violations in environment.py and weather_util.py, with max line length 100 and ignoring E203,W503
# Use black to check if the specified files are properly formatted
cd ../service_environment || exit 1
flake8 environment.py weather_util.py --max-line-length=100 --ignore=E203,W503 || exit 1
black --check --diff --line-length=100 environment.py weather_util.py || exit 1

echo "Linting complete."
