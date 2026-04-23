# EduAI

Интеллектуальная образовательная платформа на Django с сильным акцентом на инклюзивность, генеративный ИИ, TTS, мультиязычность и серверный рендеринг. Репозиторий подготовлен для публикации на GitHub: без секретов, без локальной базы, без пользовательских загрузок и без runtime-логов.

Подробная техническая документация и инструкция по деплою: [DOCS.md](DOCS.md).

## Что умеет проект

- Инклюзивное обучение: крупный шрифт, выбор гарнитур, OpenDyslexic, высокий контраст, easy-to-read, визуальные опоры, дзен-режим для снижения визуального шума, голосовой ввод и TTS.
- Генерация тестов, материалов урока и критериев оценивания.
- ИИ-чат и SSE-стриминг ответов.
- Персонализированные объяснения по теме, уровню и интересам ученика.
- Проверка эссе и отчёты по классу.
- TTS для доступности: `edge-tts` с fallback на `gTTS`, список голосов и чанковая озвучка длинных текстов.
- Мультиязычность `ru / en / kk`.
- Админ-панель, FAQ, обращения, организации и ключи доступа.

## Почему инклюзивность здесь не второстепенна

В EduAI доступность встроена в архитектуру, а не добавлена поверх интерфейса. У пользователя есть отдельный профиль доступности с настройками потребностей и предпочтений, а интерфейс и контент подстраиваются под них на уровне шаблонов, CSS, TTS и AI-модулей.

Поддерживаются:

- профили потребностей: зрение, когнитивные особенности, дислексия, слух;
- OpenDyslexic и дополнительные шрифты для кириллицы;
- масштабирование шрифта от 14 до 32 px;
- высокий контраст и сниженный визуальный шум;
- easy-to-read упрощение текста;
- озвучка текста и голосовой ввод;
- визуальные опоры и mind map-сценарии.

## Технологический стек

- Backend: Django 6, WhiteNoise, Gunicorn.
- Frontend: Django Templates, Vanilla JS, CSS Custom Properties.
- AI: provider-agnostic слой поверх OpenAI-compatible API.
- Поддерживаемые AI-провайдеры: `OpenAI`, `Google Gemini`, `Ollama`, `LM Studio`, `vLLM` и другие совместимые endpoints.
- Data: SQLite для локальной разработки, PostgreSQL для production.
- Media: Pillow, `python-magic`, `edge-tts`, `gTTS`.

## Как устроен AI-слой

Проект не привязан к одному провайдеру и не ограничивается ChatGPT/OpenAI. Файл `core/ai.py` использует OpenAI Python SDK как универсальный клиент к любому OpenAI-compatible API, поэтому провайдер меняется только через переменные окружения:

- `AI_API_KEY`
- `AI_BASE_URL`
- `AI_MODEL`

Это позволяет запускать один и тот же сайт как на OpenAI/ChatGPT API, так и на Gemini, Ollama, LM Studio или vLLM без переписывания бизнес-логики.

## Требования

- Python 3.12+
- `pip` и `venv`
- Linux/macOS/WSL для самого простого запуска
- системная библиотека `libmagic` для `python-magic`

Для Ubuntu/Debian:

```bash
sudo apt install libmagic1
```

Для macOS:

```bash
brew install libmagic
```

## Быстрый старт

```bash
git clone <repo-url> smart_school
cd smart_school

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Заполните в `.env` минимум две переменные:

- `SECRET_KEY`
- `AI_API_KEY`

После этого:

```bash
./run.sh dev
```

Сервер поднимется на `http://127.0.0.1:8000/`.

## Полезные команды

```bash
./run.sh dev      # локальный запуск
./run.sh prod     # gunicorn + migrate + collectstatic
./run.sh migrate  # makemigrations + migrate
./run.sh seed     # тестовые данные
./run.sh static   # collectstatic
./run.sh check    # Django check --deploy
```

Если нужны стартовые данные:

```bash
python manage.py seed
```

## Конфигурация окружения

Основные переменные:

| Переменная | Назначение |
|---|---|
| `SECRET_KEY` | секретный ключ Django |
| `DEBUG` | режим разработки |
| `ALLOWED_HOSTS` | список хостов через запятую |
| `CSRF_TRUSTED_ORIGINS` | список доверенных origin через запятую |
| `DATABASE_URL` | база данных (`sqlite:///...` или `postgresql://...`) |
| `AI_API_KEY` | ключ AI-провайдера |
| `AI_BASE_URL` | OpenAI-compatible base URL |
| `AI_MODEL` | имя модели |
| `AI_TIMEOUT` | таймаут запросов к AI |
| `DEFAULT_LANGUAGE` | язык интерфейса по умолчанию |
| `EMAIL_*` | SMTP-настройки, если нужен production email |

Готовые примеры есть в `.env.example`.

## Что не хранится в репозитории

При публикации на GitHub в репозиторий не должны попадать:

- `.env` и любые production secrets
- `db.sqlite3`
- `staticfiles/`
- `.cache/`
- `logs/`
- пользовательские загрузки из `media/`
- локальные cookies, временные файлы и IDE-конфиги

Это уже настроено в `.gitignore`.

## Структура проекта

```text
smart_school/
├── config/                # Django settings / urls / wsgi
├── core/                  # основное приложение
│   ├── models/            # модели по доменным модулям
│   ├── templates/core/    # серверные шаблоны
│   ├── static/core/       # CSS / JS / изображения
│   ├── management/commands/
│   ├── ai.py              # AI-клиент, промпты, retry/backoff, circuit breaker
│   ├── translations.py    # JSON-локализация
│   └── views.py           # страницы и API
├── locale/                # ru / en / kk переводы
├── media/                 # локальные загрузки, в Git не публикуются
├── logs/                  # runtime-логи, в Git не публикуются
├── requirements.txt
├── run.sh
└── Procfile
```

## Production

- `Procfile` готов для платформ, поддерживающих `gunicorn`.
- WhiteNoise обслуживает статические файлы без внешнего CDN.
- Для production рекомендуется PostgreSQL и `DEBUG=False`.
- Перед деплоем обязательно задайте `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SECRET_KEY` и AI-конфиг.
- При смене AI-провайдера обычно достаточно поменять только `AI_BASE_URL`, `AI_MODEL` и `AI_API_KEY`.

## Перед первой публикацией на GitHub

- Проверьте, что в `.env` нет реальных ключей в индексе Git.
- Убедитесь, что локальная база и пользовательские файлы не добавлены в commit.
- Добавьте лицензию, если проект будет открыт публично.

## Статус проекта

Проект ориентирован на локальную разработку и деплой на обычный Linux-хостинг или PaaS с поддержкой Python/Gunicorn.
