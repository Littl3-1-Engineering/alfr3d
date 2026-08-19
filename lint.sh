#!/bin/bash

# Linting script for Alfr3d project

echo "Running linting on all services..."

FLAKE8_IGNORE=E203,W503,E402

# Frontend (Node.js)
echo "Linting service_frontend..."
# Run npm lint to check for JavaScript/React code style and potential errors
cd services/service_frontend || exit 1
npm run lint || exit 1

# API service
echo "Linting service_api..."
# Use flake8 to check for Python style violations across the FastAPI app, its
# shared dependencies/models, and all route modules, with max line length 100.
# Use black to check if the checked files are properly formatted.
cd ../service_api || exit 1
flake8 app.py dependencies.py models.py tree_of_alfr3d.py routes/ --max-line-length=100 --ignore=$FLAKE8_IGNORE || exit 1
black --check --diff --line-length=100 app.py dependencies.py models.py tree_of_alfr3d.py routes/ || exit 1

# Daemon service
echo "Linting service_daemon..."
# Use flake8 to check for Python style violations in alfr3ddaemon.py and utils/, with max line length 100
# Use black to check if the specified files are properly formatted
cd ../service_daemon || exit 1
flake8 alfr3ddaemon.py utils/ --max-line-length=100 --ignore=$FLAKE8_IGNORE || exit 1
black --check --diff --line-length=100 alfr3ddaemon.py utils/ || exit 1

# User service
echo "Linting service_user..."
# Use flake8 to check for Python style violations in app.py, with max line length 100
# Use black to check if app.py is properly formatted
cd ../service_user || exit 1
flake8 app.py --max-line-length=100 --ignore=$FLAKE8_IGNORE || exit 1
black --check --diff --line-length=100 app.py || exit 1

# Device service
echo "Linting service_device..."
# Use flake8 to check for Python style violations in app.py, with max line length 100
# Use black to check if app.py is properly formatted
cd ../service_device || exit 1
flake8 app.py --max-line-length=100 --ignore=$FLAKE8_IGNORE || exit 1
black --check --diff --line-length=100 app.py || exit 1

# Environment service
echo "Linting service_environment..."
# Use flake8 to check for Python style violations in environment.py and weather_util.py, with max line length 100
# Use black to check if the specified files are properly formatted
cd ../service_environment || exit 1
flake8 environment.py weather_util.py --max-line-length=100 --ignore=$FLAKE8_IGNORE || exit 1
black --check --diff --line-length=100 environment.py weather_util.py || exit 1

# Speak service
echo "Linting service_speak..."
# Use flake8 to check for Python style violations in app.py, llm_client.py, and personality.py, with max line length 100
# Use black to check if the specified files are properly formatted
cd ../service_speak || exit 1
flake8 app.py llm_client.py personality.py --max-line-length=100 --ignore=$FLAKE8_IGNORE || exit 1
black --check --diff --line-length=100 app.py llm_client.py personality.py || exit 1

# Common service
echo "Linting service_common..."
# Use flake8 to check for Python style violations in the common/ shared module, with max line length 100
# Use black to check if the common/ files are properly formatted
cd ../common || exit 1
flake8 . --max-line-length=100 --ignore=$FLAKE8_IGNORE,F401 || exit 1
black --check --diff --line-length=100 . || exit 1

echo "Linting complete."
