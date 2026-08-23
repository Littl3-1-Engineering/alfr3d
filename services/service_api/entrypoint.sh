#!/bin/bash
chown -R 1000:1000 /tmp/audio
chown -R 1000:1000 /secrets
exec "$@"
