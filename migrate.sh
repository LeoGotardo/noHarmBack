#!/bin/bash
set -e
echo "Rodando migrations..."
ENV=production alembic upgrade head
echo "Migrations concluídas."