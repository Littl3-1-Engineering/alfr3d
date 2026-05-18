#!/bin/bash
mkdir -p /tmp/audio
chown -R 1000:1000 /tmp/audio
exec "$@"
