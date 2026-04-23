#!/usr/bin/env bash
# ============================================================
# EduAI — скрипт запуска
# Использование: ./run.sh [dev|prod|migrate|seed|static]
# ============================================================
set -e

# Определяем директорию проекта
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Активация venv если есть
if [ -f "../ai_venv/bin/activate" ]; then
    source ../ai_venv/bin/activate
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

case "${1:-dev}" in
    dev)
        echo "🚀 Запуск dev-сервера..."
        python manage.py migrate --noinput
        python manage.py collectstatic --noinput
        python manage.py runserver 0.0.0.0:8000
        ;;
    prod)
        echo "🚀 Запуск production-сервера (gunicorn)..."
        python manage.py migrate --noinput
        python manage.py collectstatic --noinput
        gunicorn config.wsgi --bind 0.0.0.0:${PORT:-8000} --workers 3 --timeout 120
        ;;
    migrate)
        echo "📦 Миграции..."
        python manage.py makemigrations
        python manage.py migrate
        ;;
    seed)
        echo "🌱 Заполнение тестовыми данными..."
        python manage.py seed
        ;;
    static)
        echo "📁 Сборка статики..."
        python manage.py collectstatic --noinput
        ;;
    check)
        echo "🔍 Проверка проекта..."
        python manage.py check --deploy
        ;;
    *)
        echo "Использование: ./run.sh [dev|prod|migrate|seed|static|check]"
        exit 1
        ;;
esac
