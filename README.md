# Информационная система учета входящей корреспонденции

REST API для централизованного электронного учета входящих документов организации: регистрация с автоматическим номером, поиск и фильтрация, резолюции руководителя, назначение исполнителей, контроль сроков, вложения в S3-хранилище, журнал действий, архив, PDF-отчеты и CSV-выгрузка журнала регистрации. Права доступа проверяются на backend. Веб-интерфейс (HTML + Vanilla JS, без сборки) раздается тем же FastAPI по адресу **`/ui`** и работает только через REST API.

## Стек

| Уровень | Технологии |
|---|---|
| Backend | Python 3.14, FastAPI, Pydantic v2 и Pydantic Settings, SQLAlchemy 2.x (async), asyncpg, Alembic |
| Веб-интерфейс | HTML, CSS, Vanilla JS (ES-модули), Fetch API; без npm, сборщиков и фреймворков; раздается через `StaticFiles` |
| Данные | PostgreSQL 18, MinIO (S3 API) через aioboto3 |
| Безопасность | JWT (PyJWT), argon2 (argon2-cffi), RBAC на зависимостях FastAPI |
| Отчеты | ReportLab (PDF, шрифт DejaVu Sans с кириллицей), CSV (UTF-8 BOM, `;`) |
| Инфраструктура | Docker, Docker Compose, volumes, healthcheck, `restart: unless-stopped` |
| Качество | pytest, pytest-asyncio, httpx, ruff |

Документация: [архитектура](docs/architecture.md) · [варианты использования](docs/use-case.md) · [состояния](docs/state-diagram.md) · [схема данных](docs/data-schema.md) · [тест-кейсы](docs/test-cases.md) · [допущения](docs/assumptions.md).

## Требования к окружению

- Docker Engine 24+ и плагин Docker Compose v2 (`docker compose version`);
- свободные порты 8000 (API), а также 5432, 9000, 9001 на `127.0.0.1`;
- 2 ГБ RAM, 2 ГБ диска.

**AlmaLinux 10:**

```bash
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker          # Docker и контейнеры поднимаются после перезагрузки
sudo usermod -aG docker "$USER"             # затем перелогиниться
sudo firewall-cmd --permanent --add-port=8000/tcp && sudo firewall-cmd --reload
```

SELinux можно оставить в режиме enforcing: bind-mount каталога `backups` помечен `:z`.

## Запуск через Docker

```bash
cp .env.example .env
# обязательно замените пароли и JWT_SECRET, например:
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

docker compose up -d --build
docker compose ps                          # backend, postgres, minio — healthy
curl http://localhost:8000/health          # {"status":"ok","database":"ok","storage":"ok"}
```

- Веб-интерфейс: **http://localhost:8000/ui** (адрес `http://localhost:8000/` перенаправляет туда же). Вход — учетными записями из seed (см. ниже).
- Swagger UI: **http://localhost:8000/docs**. Вход: `POST /api/v1/auth/login` → скопировать `access_token` → кнопка **Authorize**.
- Health-check: **http://localhost:8000/health** (также `/api/v1/health`).
- Консоль MinIO: http://127.0.0.1:9001 (логин и пароль — `S3_ACCESS_KEY` / `S3_SECRET_KEY`).

Данные хранятся в именованных томах `postgres_data` и `minio_data` и переживают `docker compose restart`, `docker compose down` (без `-v`) и перезагрузку хоста. Backend корректно завершает работу по SIGTERM (`docker compose stop`).

## Миграции

Миграции применяются автоматически при каждом старте backend. Ручной запуск:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
```

## Seed-данные

```bash
docker compose exec backend python -m scripts.seed
```

Seed создает 3 подразделения, 5 должностей, 8 типов документов, 10 корреспондентов, 5 пользователей и 20 документов во всех статусах: с резолюциями, историей, просроченными и близкими к сроку. Повторный запуск ничего не дублирует. Все персональные данные вымышлены.

### Тестовые учетные записи

| Логин | Пароль | Роль |
|---|---|---|
| `admin` | `admin123` | Администратор |
| `clerk` | `clerk123` | Делопроизводитель |
| `manager` | `manager123` | Руководитель |
| `executor1` | `executor123` | Исполнитель |
| `executor2` | `executor123` | Исполнитель |

## Веб-интерфейс

Открывается по адресу **http://localhost:8000/ui** после `docker compose up -d` и загрузки seed-данных. Отдельный контейнер, Node.js и сборка не нужны: каталог `ui/` копируется в образ backend вместе с кодом, и FastAPI раздает его как статику (`app/main.py`, `app.mount("/ui", StaticFiles(...))`). Swagger остается на `/docs`.

```
ui/
├── index.html   каркас: форма входа, шапка, меню, область содержимого, контейнеры уведомлений и диалогов
├── api.js       HTTP-клиент: JWT в заголовке Authorization, разбор ошибок {detail, code, field}, обработка 401, скачивание файлов
├── app.js       маршрутизация по #-адресам, экраны ролей, формы, валидация, уведомления, диалоги подтверждения
└── styles.css   оформление
```

**Авторизация.** Логин и пароль отправляются в `POST /api/v1/auth/login`. В `localStorage` сохраняется только JWT, пароль не сохраняется нигде. Токен подставляется в каждый запрос как `Authorization: Bearer …`. Любой ответ 401 очищает токен и возвращает на форму входа; после повторного входа открывается тот же раздел. Кнопка «Выйти» находится в шапке.

**Разграничение доступа.** Меню и кнопки строятся по роли и списку разрешений из `GET /api/v1/auth/me`. Это только удобство: скрытая кнопка не защищает. Все проверки прав и бизнес-правил выполняет backend, а интерфейс показывает его ответ.

### Экраны по ролям

| Роль | Разделы меню | Действия в интерфейсе |
|---|---|---|
| Делопроизводитель (`clerk`) | Журнал документов, Регистрация документа, Корреспонденты, Отчёты и выгрузка | поиск, фильтры (статус, тип, корреспондент, даты, контроль срока), сортировка, пагинация; регистрация с отдельной кнопкой «Прикрепить скан»; редактирование реквизитов; загрузка и скачивание файлов; смена статуса: зарегистрирован → на рассмотрении, исполнен → снят с контроля, снят с контроля → в архиве (с подтверждением); корреспонденты: список, поиск, создание, редактирование; три PDF-отчета; CSV-выгрузка журнала |
| Руководитель (`manager`) | Журнал документов, Отчёты | поиск и фильтры (в том числе по исполнителю), карточка, «Добавить резолюцию» (исполнитель из `GET /users/executors`), «Изменить резолюцию», просмотр резолюций, PDF-отчеты |
| Исполнитель (`executor`) | Мои поручения | только документы, где он назначен исполнителем; карточка с резолюцией; загрузка отчетных материалов; «Отметить исполнение»; история |
| Администратор (`admin`) | Документы, Пользователи, Справочники | пользователи: список, фильтры, создание, редактирование, деактивация с подтверждением; справочники: подразделения, должности, типы документов; карточки только для просмотра, открытие по регистрационному номеру, аннулирование и «Удалить карточку» с подтверждением |

Карточка документа содержит вкладки «Основные сведения», «Вложения» (кнопка «Скачать» у каждого файла), «Резолюции», «История», «Управление статусом». В журнале просроченные документы выделены красным, документы с близким сроком — желтым. Признак берется из поля `deadline_state` ответа API и дублируется текстом в колонке «Срок» («просрочен на 3 дня», «срок близок: осталось 2 дня»). Статусы показываются текстом и цветом.

Некоторые справочники роли не выдаются API, поэтому соответствующих фильтров у нее нет. Руководителю недоступен список корреспондентов: он ищет корреспондента через строку поиска, которая охватывает и наименование корреспондента. Делопроизводителю недоступен список исполнителей. У исполнителя и администратора поиска по журналу нет; администратор открывает карточку по точному регистрационному номеру.

### Ошибки и проверки

| Ответ API | Что показывает интерфейс |
|---|---|
| 401 | очистка токена, форма входа с сообщением о завершении сессии |
| 403 | уведомление «Нет доступа»; для деактивированной учетной записи — выход и сообщение на форме входа |
| 404 | уведомление «Не найдено» |
| 409 | уведомление с текстом `detail`; если в ответе есть `field`, поле подсвечивается |
| 413 | уведомление «Файл слишком большой» |
| 422 | подсветка поля из `field` и текст `detail` рядом с ним |

Перед отправкой формы интерфейс проверяет обязательные поля, формат email, ИНН (10 или 12 цифр), `page_count ≥ 1`, срок исполнения не раньше даты регистрации, тип файла (PDF, JPG, PNG, DOCX) и размер до 20 МБ. Эти проверки только ускоряют обратную связь, окончательное решение принимает сервер. Каждая загрузка данных показывает индикатор, пустой результат — «Нет данных» с подсказкой, ошибка загрузки — кнопку «Повторить».

Интерфейс рассчитан на современные браузеры с поддержкой ES-модулей (Chrome, Edge, Firefox, Safari последних версий) и ширину окна от 1280 пикселей; на более узких экранах меню переносится наверх.

## Матрица ролей и разрешений

Единственный источник истины — `app/security/permissions.py`.

| Разрешение | Делопроизводитель | Руководитель | Исполнитель | Администратор |
|---|:-:|:-:|:-:|:-:|
| Авторизация | ✅ | ✅ | ✅ | ✅ |
| Пользователи: регистрация, просмотр, редактирование, деактивация | | | | ✅ |
| Справочники: подразделения, должности, типы документов | | | | ✅ |
| Корреспонденты: создание, редактирование, просмотр | ✅ | | | |
| Регистрация карточки | ✅ | | | |
| Редактирование карточки (до архива) | ✅ | | | |
| Просмотр карточки, истории, файлов | ✅ | ✅ | ✅ свои¹ | ✅ чтение² |
| Поиск и фильтрация | ✅ | ✅ | | |
| Удаление карточки | | | | ✅ |
| Создание и редактирование резолюции | | ✅ | | |
| Просмотр резолюций | ✅ | ✅ | ✅ свои¹ | |
| Прикрепление файла | ✅ скан | | ✅ отчет¹ | |
| Смена статуса | ✅ | авто³ | ✅ исполнение¹ | ✅ аннулирование |
| Формирование отчета (PDF) | ✅ | ✅ | | |
| Выгрузка журнала (CSV) | ✅ | | | |

¹ Только документы, по которым пользователю назначена резолюция (контекстная проверка в сервисе).
² Администратор видит карточки только для того, чтобы проверить документ перед удалением или аннулированием; поиск ему недоступен ([допущение A-2](docs/assumptions.md)).
³ «На рассмотрении → на исполнении» выполняется автоматически при создании резолюции.

Коды ответов: 401 — нет или недействительный токен; 403 — роль или контекст не позволяет действие (или пользователь деактивирован); 404 — объект не найден; 409 — недопустимый переход статуса, дубликат, архив; 413 — файл больше лимита; 422 — ошибка валидации. Формат ошибки единый:

```json
{"detail": "Переход «зарегистрирован» → «исполнен» недопустим", "code": "INVALID_STATUS_TRANSITION", "field": "status"}
```

## API (префикс `/api/v1`)

| Метод и путь | Назначение | Роли |
|---|---|---|
| `POST /auth/login` | Вход, JWT, данные пользователя и роль | все |
| `GET /auth/me` | Текущий пользователь и его разрешения | все |
| `POST /users` · `GET /users` · `GET /users/{id}` · `PATCH /users/{id}` · `POST /users/{id}/deactivate` | Управление пользователями | admin |
| `GET /users/executors` | Активные исполнители для назначения резолюций | manager, admin |
| `GET/POST /departments`, `PATCH /departments/{id}` | Подразделения | admin |
| `GET/POST /positions`, `PATCH /positions/{id}` | Должности | admin |
| `GET /document-types` · `POST` · `PATCH /{id}` | Типы документов (чтение — все) | admin |
| `POST /correspondents` · `GET /correspondents` · `GET /{id}` · `PATCH /{id}` | Корреспонденты | clerk |
| `POST /incoming` | Регистрация: номер и дата присваиваются сервером | clerk |
| `GET /incoming` | Список, поиск, фильтры, пагинация, сортировка | все (с учетом прав) |
| `GET /incoming/{id}` · `GET /incoming/by-registration-number/{номер}` | Карточка: реквизиты, резолюции, вложения, история, сроки | все (с учетом прав) |
| `PATCH /incoming/{id}` | Редактирование (кроме архива) | clerk |
| `DELETE /incoming/{id}` | Удаление (ошибка, дубликат) | admin |
| `POST /incoming/{id}/status` | Смена статуса по матрице переходов | clerk, executor, admin |
| `GET /incoming/{id}/history` | История действий | все (с учетом прав) |
| `POST /incoming/{id}/resolutions` · `GET /incoming/{id}/resolutions` | Резолюции | manager / просмотр |
| `PATCH /resolutions/{id}` | Редактирование резолюции | manager |
| `POST /incoming/{id}/files` | Файл PDF/JPG/PNG/DOCX, multipart (`file`, `attachment_type`) | clerk, executor |
| `GET /files/{id}/download` | Скачивание (потоком, после RBAC) | все (с учетом прав) |
| `POST /reports/generate` | PDF: `documents`, `executors`, `deadlines` | clerk, manager |
| `GET /exports/registration-log` | CSV журнала регистрации | clerk |
| `GET /health` | БД, S3, сервис | без авторизации |

Параметры `GET /incoming`: `page`, `page_size` (≤ 100), `sort` (например, `-registration_date,registration_number`), `registration_number`, `date_from`, `date_to` (по дате регистрации), `correspondent_id`, `executor_id`, `status`, `document_type_id`, `search` (ключевые слова), `deadline_state` (`overdue` | `warning`).

## Пример сценария через curl

```bash
API=http://localhost:8000/api/v1
tok() { curl -s -X POST $API/auth/login -H 'Content-Type: application/json' \
          -d "{\"login\":\"$1\",\"password\":\"$2\"}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])'; }
CLERK=$(tok clerk clerk123); MANAGER=$(tok manager manager123)

CORR=$(curl -s $API/correspondents -H "Authorization: Bearer $CLERK" | python3 -c 'import sys,json;print(json.load(sys.stdin)["items"][0]["id"])')
TYPE=$(curl -s $API/document-types -H "Authorization: Bearer $CLERK" | python3 -c 'import sys,json;print(json.load(sys.stdin)[0]["id"])')

curl -s -X POST $API/incoming -H "Authorization: Bearer $CLERK" -H 'Content-Type: application/json' -d "{
  \"received_date\":\"$(date +%F)\", \"correspondent_id\":\"$CORR\", \"summary\":\"Запрос сведений\",
  \"document_type_id\":\"$TYPE\", \"page_count\":2, \"execution_deadline\":\"$(date -d '+10 day' +%F)\"}"

curl -s "$API/exports/registration-log" -H "Authorization: Bearer $CLERK" -o journal.csv
curl -s -X POST $API/reports/generate -H "Authorization: Bearer $MANAGER" -H 'Content-Type: application/json' \
     -d "{\"report_type\":\"executors\",\"period_from\":\"$(date -d '-60 day' +%F)\",\"period_to\":\"$(date +%F)\"}" -o report.pdf
```

## Backup и restore

```bash
scripts/backup_db.sh                                     # → backups/db/db_YYYYMMDD_HHMMSS.dump (pg_dump -Fc)
scripts/backup_storage.sh                                # → backups/storage/storage_YYYYMMDD_HHMMSS/ (mc mirror)

scripts/restore_db.sh backups/db/db_20260930_120000.dump            # пересоздает БД, backend на время останавливается
scripts/restore_storage.sh backups/storage/storage_20260930_120000
```

**Проверка восстановления на чистой среде:**

```bash
scripts/backup_db.sh && scripts/backup_storage.sh
docker compose down -v                                  # удалить контейнеры и тома (данные исчезнут)
docker compose up -d --wait                             # чистая система, миграции применены
scripts/restore_db.sh backups/db/<файл>.dump
scripts/restore_storage.sh backups/storage/<каталог>
# проверить: вход clerk/clerk123, GET /api/v1/incoming — прежние документы;
# GET /api/v1/files/{id}/download — прежние файлы скачиваются
```

Для регулярного копирования добавьте оба скрипта в cron хоста, например `0 2 * * * cd /opt/correspondence && scripts/backup_db.sh && scripts/backup_storage.sh`.

## Тесты

```bash
docker compose up -d --wait postgres minio
docker compose --profile test run --rm tests                                  # все тесты
docker compose --profile test run --rm tests python -m pytest tests/unit -q   # только unit
docker compose --profile test run --rm tests ruff check .                      # линтер
```

Тест `tests/integration/test_ui_static.py` проверяет, что веб-интерфейс раздается по `/ui` с правильными MIME-типами, а `/` перенаправляет на него.

Интеграционные тесты сами создают отдельную БД `<POSTGRES_DB>_test` и бакет `correspondence-test`, прогоняют миграции вниз и вверх и очищают данные перед каждым тестом. Рабочие данные не затрагиваются. Описание кейсов и результаты — в [docs/test-cases.md](docs/test-cases.md).

**Локальная разработка без контейнера backend** (Python 3.14):

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
docker compose up -d postgres minio
# в .env заменить хосты postgres/minio на localhost
alembic upgrade head && uvicorn app.main:app --reload
pytest
```

## Переменные окружения

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://…` | — (обязательна) |
| `JWT_SECRET` | секрет подписи JWT (≥ 16 символов, рекомендуется ≥ 32) | — (обязательна) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | срок жизни токена | 60 |
| `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `S3_REGION` | MinIO / S3 | — / `us-east-1` |
| `MAX_UPLOAD_SIZE_MB` | лимит размера файла | 20 |
| `REG_NUMBER_TEMPLATE` | шаблон номера | `ВХ-{YYYY}-{NNNNNN}` |
| `DEADLINE_WARNING_DAYS` | за сколько дней предупреждать о сроке | 3 |
| `APP_TIMEZONE` | часовой пояс организации | `Europe/Moscow` |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | инициализация контейнера PostgreSQL | — |
| `LOG_LEVEL`, `PDF_FONT_PATH` | уровень логов, путь к TTF для PDF | `INFO`, автопоиск DejaVu |

Секреты хранятся только в `.env`: файл исключен из git и из Docker-образа.
