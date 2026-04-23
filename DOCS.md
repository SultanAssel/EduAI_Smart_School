# EduAI — документация по запуску, архитектуре и деплою

Актуальная рабочая документация для локальной разработки, подготовки репозитория к GitHub и выкладки в production. Отдельно подчёркнуты две ключевые особенности платформы: инклюзивность как часть продуктовой архитектуры и мультипровайдерный AI-слой.

## 0. Что важно понимать о проекте

EduAI не является просто «сайтом с ChatGPT». Это серверная образовательная платформа с несколькими независимыми подсистемами:

- инклюзивный интерфейс и профиль доступности;
- AI-модуль с переключаемым провайдером;
- TTS и голосовой ввод;
- SSR-интерфейс на Django templates;
- учебные модули: тесты, уроки, эссе, отчёты, FAQ, организации.

Из этого следуют два важных технических вывода:

1. AI API здесь не только OpenAI/ChatGPT, а любой OpenAI-compatible backend.
2. Доступность здесь не декоративная: она влияет на данные профиля, интерфейс, стили, озвучку и AI-сценарии упрощения текста.

## 1. Системные требования

- Python 3.12+
- `pip` и `venv`
- Linux/macOS/WSL для самого простого запуска
- `libmagic` в системе, так как проект использует `python-magic`

Установка `libmagic`:

```bash
# Ubuntu / Debian
sudo apt install libmagic1

# macOS
brew install libmagic
```

## 2. Прямые Python-зависимости

Файл `requirements.txt` содержит только прямые зависимости проекта:

- `Django`
- `python-dotenv`
- `dj-database-url`
- `whitenoise`
- `gunicorn`
- `openai`
- `Pillow`
- `python-magic`
- `edge-tts`
- `gTTS`
- `psycopg2-binary` как драйвер для PostgreSQL

Если проект разворачивается только на SQLite, `psycopg2-binary` просто не будет использоваться.

## 2.1. Инклюзивность и доступность

Инклюзивность в проекте реализована не одной страницей, а несколькими связанными слоями:

- `AccessibilityProfile` хранит пользовательские настройки доступности;
- `core/context_processors.py` пробрасывает их в шаблоны;
- `core/templates/core/base.html` вешает соответствующие `data-*` атрибуты на `<html>`;
- `core/static/core/css/accessibility.css` перестраивает интерфейс под активные режимы;
- `core/ai.py` имеет отдельный сценарий `EASY_READ` для упрощения текста;
- TTS и voice input доступны как отдельные API/UX-сценарии.

Фактические возможности по коду:

- primary need: `vision`, `cognitive`, `dyslexia`, `hearing`;
- font size: от 14 до 32 px;
- font family: `default`, `OpenDyslexic`, `Comfortaa`, `PT Sans`, `Pangolin`, `Arial`, `Verdana`, `Georgia`, `Times New Roman`, `Courier New`;
- высокий контраст;
- text-to-speech;
- easy-read упрощение текста;
- visual aids;
- zen mode для снижения визуального шума и поддержки пользователей с СДВГ;
- голосовой ввод.

Это одна из ключевых частей продукта, и при описании проекта на GitHub её нужно выносить явно, а не прятать в конец README.

## 3. Локальный запуск

```bash
git clone <repo-url> smart_school
cd smart_school

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Минимально обязательные переменные в `.env`:

```env
SECRET_KEY=your-secret-key
AI_API_KEY=your-provider-key
```

Запуск:

```bash
./run.sh dev
```

Дополнительно:

```bash
./run.sh migrate
./run.sh seed
./run.sh check
```

## 4. Переменные окружения

### Django

| Переменная | Обязательность | Примечание |
|---|---|---|
| `SECRET_KEY` | обязательно | в production нельзя оставлять пустым |
| `DEBUG` | обязательно для prod | `False` в production |
| `ALLOWED_HOSTS` | обязательно для prod | список через запятую |
| `CSRF_TRUSTED_ORIGINS` | желательно для prod | особенно за reverse proxy |
| `DEFAULT_LANGUAGE` | опционально | `ru`, `en` или `kk` |

### Database

| Переменная | Пример |
|---|---|
| `DATABASE_URL` | `sqlite:///db.sqlite3` |
| `DATABASE_URL` | `postgresql://user:pass@host:5432/dbname` |

### AI / LLM

| Переменная | Пример |
|---|---|
| `AI_API_KEY` | ключ провайдера |
| `AI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `AI_MODEL` | `gemini-2.5-flash` |
| `AI_TIMEOUT` | `25` |

Проект работает с OpenAI-compatible API, поэтому можно переключать бэкенд без переписывания кода.

Поддерживаемые сценарии:

- OpenAI / ChatGPT API;
- Google Gemini через OpenAI-compatible endpoint;
- локальный Ollama;
- LM Studio;
- vLLM;
- любой другой совместимый endpoint.

Практически это означает, что сайт не жёстко прибит к одному AI-сервису: инфраструктура может быть облачной, локальной или гибридной.

### Email

Если нужны реальные письма, заполните `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`.

## 5. Что делает `run.sh`

| Команда | Действие |
|---|---|
| `./run.sh dev` | `migrate + collectstatic + runserver` |
| `./run.sh prod` | `migrate + collectstatic + gunicorn` |
| `./run.sh migrate` | `makemigrations + migrate` |
| `./run.sh seed` | загрузка тестовых данных |
| `./run.sh static` | сборка статики |
| `./run.sh check` | `python manage.py check --deploy` |

## 6. Production deployment

Минимальный production-план:

1. Создать `.env` с `DEBUG=False`.
2. Настроить `ALLOWED_HOSTS` и `CSRF_TRUSTED_ORIGINS`.
3. Подключить PostgreSQL через `DATABASE_URL`.
4. Выполнить `./run.sh prod` или использовать `Procfile`.
5. Отдать трафик через reverse proxy с HTTPS.

`Procfile` уже содержит:

- `web`: запуск `gunicorn`
- `release`: `migrate + collectstatic`

## 7. Что исключено из Git

В репозиторий не должны попадать:

- `.env` и любые секреты
- `db.sqlite3`
- `staticfiles/`
- `.cache/`
- `logs/`
- пользовательские загрузки из `media/`
- `cookies.txt`
- кэши IDE, coverage и временные файлы

Для этого обновлён `.gitignore`. Внутри `media/` и `logs/` допускаются только `.gitkeep`.

## 8. Структура проекта

```text
config/            Django settings, urls, wsgi
core/
  models/          доменные модели
  templates/core/  SSR-шаблоны
  static/core/     CSS, JS, assets
  ai.py            клиент AI-провайдера, промпты, retry/backoff, circuit breaker
  translations.py  ru/en/kk JSON-локализация
  views.py         страницы и API
locale/            словари переводов
media/             локальные пользовательские файлы
logs/              runtime-логи
run.sh             сценарии запуска
Procfile           PaaS/Gunicorn entrypoints
```

## 9. Проверка перед публикацией на GitHub

Перед первым push проверьте:

1. В индексе Git нет `.env`, `db.sqlite3`, `media/*`, `logs/*`, `staticfiles/*`.
2. README описывает актуальный стек и запуск.
3. `.env.example` не содержит реальных ключей.
4. `requirements.txt` отражает прямые зависимости проекта.
5. `python manage.py check` проходит без ошибок.

## 10. Частые проблемы

### `python-magic` не работает

Проверьте, что в системе установлен `libmagic`.

### AI-запросы не проходят

Проверьте `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL` и доступность внешнего API.

### В production не отдаются статика или формы падают по CSRF

Проверьте:

- `collectstatic`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- HTTPS / reverse proxy headers

### Озвучка (TTS)

| Эндпоинт | Метод | Тело/Параметры | Описание |
|---|---|---|---|
| `/api/tts/` | POST | `{text, voice?, rate?}` | Генерация аудио через edge-tts (Microsoft Neural TTS). `voice` — ID голоса (напр. `ru-RU-SvetlanaNeural`), `rate` — скорость (`+20%`, `-10%`). Без `voice` язык определяется автоматически. |
| `/api/tts/chunked/` | POST | `{action, text?, session_id?, chunk_index?, voice?, rate?}` | Чанковая TTS для длинных текстов. `action=prepare` — разбивает текст на части по предложениям (≤ 2500 символов), возвращает `session_id` + инфо о чанках. `action=chunk` — возвращает audio/mpeg для конкретного чанка. |
| `/api/tts/voices/` | GET | — | Список доступных голосов (кэш 1 час, fallback на 11 встроенных голосов при ошибке). Возвращает `{voices: [{id, name, lang, gender}]}` |

---

## Авторизация и профиль

Авторизация реализована через Django-сессии (не `django.contrib.auth`).

При входе в сессию записываются:
- `user_id` — ID пользователя
- `username` — имя
- `email` — почта
- `user_role` — `student` или `teacher`
- `user_avatar` — URL аватара
- `theme` — текущая тема
- `language` — текущий язык

Роли:
- **student** — доступ ко всем модулям кроме «Ассистент учителя»
- **teacher** — полный доступ + генерация тестов + отчёты по классу
- **school_admin** — администратор школы и пользователей своей организации
- **admin** — администратор платформы

---

## AI-сервис

Файл `core/ai.py` — обёртка над OpenAI Python SDK, используемым как универсальный транспорт к любому OpenAI-compatible API.

Поддерживает любой OpenAI-совместимый API:
- Google Gemini (`generativelanguage.googleapis.com`)
- OpenAI (`api.openai.com`)
- Ollama (`localhost:11434`)
- LM Studio, vLLM и др.

Это принципиально важно для архитектуры проекта: один и тот же код может работать как с ChatGPT/OpenAI, так и с Gemini или локальной моделью, если backend понимает OpenAI-compatible запросы.

### Надёжность

- **Circuit breaker**: при ошибке инициализации клиент блокируется на 60с
- **Retry с backoff**: до 3 попыток с экспоненциальным ожиданием (1.5с → 3с → 6с)
- **Smart retry**: не повторяет при ошибках авторизации, квоты и невалидных запросов (401/403/400)
- **Кэш**: состояние клиента в Django cache (общее для Gunicorn workers)

### Валидация ответов

- **Тесты**: проверка типов вопросов, баллов, опций
- **Эссе**: ограничение баллов 0–100, дефолты для всех полей
- **Mind-карты**: валидация цветов (hex), дефолтная палитра
- **JSON**: 3-уровневый парсинг (raw → markdown code block → балансировка скобок)

### Функции

| Функция | Описание |
|---|---|
| `chat(messages, lang)` | Обычный чат-ответ |
| `stream(messages, lang)` | Генератор для SSE-стриминга |
| `generate_test(source_text, subject, grade, variant)` | Генерация теста → JSON |
| `check_essay(text, topic, subject)` | Проверка эссе → JSON с баллами |
| `simplify_text(text)` | Упрощение текста (easy-to-read) |
| `generate_mindmap(text)` | Генерация mind-карты → JSON |
| `personalize_explanation(topic, ...)` | Персонализированное объяснение |
| `generate_class_report(data)` | Генерация отчёта по классу |
| `generate_lesson_content(topic, subject, grade, request)` | Генерация контента урока |

### Где AI связан с инклюзивностью

- `simplify_text(text)` обслуживает сценарий easy-to-read;
- TTS-endpoints дополняют визуальные сценарии озвучкой;
- персонализация объяснений позволяет подстраивать под стиль и уровень ученика;
- mind map используется как визуальная опора.

---

## Системные промты

8 специализированных системных промтов для разных задач:

1. **CHAT** — EduAI-ассистент, объясняет темы, помогает с учёбой
2. **TEST_GEN** — генерация тестов в формате JSON с вопросами, вариантами, ответами
3. **ESSAY_CHECK** — семантическая проверка эссе, оценка по 4 критериям
4. **EASY_READ** — упрощение текста для людей с особыми потребностями
5. **MINDMAP** — генерация структуры mind-карты в JSON
6. **PERSONALIZE** — объяснение темы с учётом стиля, интересов, уровня
7. **CLASS_REPORT** — аналитический отчёт по успеваемости класса
8. **LESSON_PLAN** — генерация плана и контента урока

---

## Темизация

Тема хранится в `data-theme` атрибуте `<html>`:
- `light` — светлая (по умолчанию)
- `dark` — тёмная

Переключение: JS (`main.js`) + API `/api/theme/`.
Все цвета определены через CSS Custom Properties в `:root` / `[data-theme="dark"]`.

### Язык

Поддерживается: `ru` (русский), `en` (английский), `kk` (казахский).
Хранится в сессии, переключается через `/api/language/`.

### Accessibility runtime

В рантайме активные режимы пробрасываются в `<html>` через атрибуты:

- `data-font-size`
- `data-font`
- `data-high-contrast`
- `data-easy-read`
- `data-tts`
- `data-zen`

За счёт этого интерфейс меняется глобально, а не только на одной странице настроек.

---

## Конфигурация

### settings.py

| Параметр | Значение |
|---|---|
| `LANGUAGE_CODE` | `ru` |
| `TIME_ZONE` | `Asia/Almaty` |
| `STATICFILES_STORAGE` | WhiteNoise CompressedManifest |
| `CACHES` | Файловый кеш (`.cache/`), TTL 5 мин |
| Безопасность (prod) | HSTS, secure cookies, SSL redirect |

### Зависимости

- `Django>=6.0,<7.0`
- `python-dotenv>=1.2,<2.0`
- `dj-database-url>=3.1,<4.0`
- `whitenoise>=6.12,<7.0`
- `gunicorn>=24.1,<25.0`
- `openai>=2.16,<3.0`
- `Pillow>=12.1,<13.0`
- `python-magic>=0.4.27,<0.5`
- `edge-tts>=7.2,<8.0`
- `gTTS>=2.5,<3.0`
- `psycopg2-binary>=2.9,<3.0`
