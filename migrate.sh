#!/bin/bash
set -e
echo "Running migrations..."
ENV=production alembic upgrade head
echo "Migrations complete."