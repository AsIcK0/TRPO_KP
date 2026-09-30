# Схема данных

СУБД — PostgreSQL 18. Схема создается миграцией Alembic `alembic/versions/0001_initial.py`, ORM-модели описаны в `app/models/entities.py`. Тест `tests/integration/test_docs_schema.py` сверяет ER-диаграмму ниже с ORM-моделями (набор таблиц и столбцов).

```mermaid
erDiagram
    departments ||--o{ users : "department_id"
    positions |o--o{ users : "position_id"
    users ||--o{ incoming_documents : "created_by"
    correspondents ||--o{ incoming_documents : "correspondent_id"
    document_types ||--o{ incoming_documents : "document_type_id"
    incoming_documents ||--o{ resolutions : "document_id"
    users ||--o{ resolutions : "author_id"
    users ||--o{ resolutions : "assigned_executor_id"
    incoming_documents ||--o{ attachments : "document_id"
    users ||--o{ attachments : "uploaded_by"
    incoming_documents ||--o{ document_history : "document_id"
    users ||--o{ document_history : "user_id"

    departments {
        uuid id PK
        varchar name UK
        timestamptz created_at
        timestamptz updated_at
    }
    positions {
        uuid id PK
        varchar name UK
    }
    document_types {
        uuid id PK
        varchar name UK
        boolean is_active
    }
    users {
        uuid id PK
        varchar full_name
        varchar login UK
        varchar email UK
        varchar password_hash "argon2, в API не возвращается"
        varchar role "clerk|manager|executor|admin"
        uuid department_id FK
        uuid position_id FK "nullable"
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
    }
    correspondents {
        uuid id PK
        varchar name
        varchar inn "10 или 12 цифр, nullable"
        text address
        varchar phone
        varchar email
        varchar signer_full_name
        timestamptz created_at
        timestamptz updated_at
    }
    registration_counters {
        int year PK "год или 0 для сквозной нумерации"
        int last_value
    }
    incoming_documents {
        uuid id PK
        varchar registration_number UK
        date received_date
        date registration_date "проставляется системой"
        uuid correspondent_id FK
        varchar addressee
        text summary "GIN pg_trgm"
        uuid document_type_id FK
        int page_count "CHECK >= 1"
        date execution_deadline "CHECK >= registration_date"
        varchar status
        uuid created_by FK
        timestamptz archived_at "NOT NULL только в архиве"
        timestamptz created_at
        timestamptz updated_at
    }
    resolutions {
        uuid id PK
        uuid document_id FK
        text text
        uuid author_id FK "руководитель"
        uuid assigned_executor_id FK "исполнитель"
        date deadline
        varchar status "на исполнении|исполнена"
        timestamptz executed_at
        timestamptz created_at
        timestamptz updated_at
    }
    attachments {
        uuid id PK
        uuid document_id FK
        varchar original_filename
        varchar storage_key UK "генерируется сервером"
        varchar content_type
        int size_bytes "CHECK > 0"
        varchar attachment_type "source_scan|execution_report|other"
        uuid uploaded_by FK
        timestamptz created_at
    }
    document_history {
        uuid id PK
        uuid document_id FK
        uuid user_id FK
        varchar action
        varchar old_status
        varchar new_status
        text comment
        jsonb metadata
        timestamptz created_at
        bigint seq UK "IDENTITY, стабильный порядок"
    }
```

## Сущности и правила

**users.** Пароль хранится только как argon2-хэш; поле `password_hash` отсутствует во всех схемах ответа. Пользователь не удаляется физически (эндпоинта удаления нет, внешние ключи `ON DELETE RESTRICT`), вместо этого выполняется деактивация (`is_active = false`). Деактивированный пользователь не может войти, а уже выданный ему токен перестает работать сразу, потому что активность и роль читаются из БД при каждом запросе.

**incoming_documents.** Регистрационный номер уникален на уровне БД (`UNIQUE`). Дата регистрации ставится сервером (часовой пояс `APP_TIMEZONE`). Ограничения `CHECK`: `page_count >= 1`, `execution_deadline >= registration_date`, допустимые значения `status`, а также согласованность архива: `archived_at` заполнен тогда и только тогда, когда статус «в архиве».

**registration_counters.** Счетчики номеров. Инкремент выполняется одним оператором `INSERT … ON CONFLICT DO UPDATE … RETURNING`, который блокирует строку счетчика до конца транзакции регистрации. Параллельные регистрации поэтому получают разные номера, а при откате транзакции счетчик откатывается вместе с ней, и пропусков нет. Если в шаблоне номера есть год, нумерация начинается заново каждый год, иначе ведется сквозная (ключ `0`).

**resolutions.** Один документ может иметь несколько резолюций. Каждая резолюция относится к одному документу и одному исполнителю. Автор — только руководитель (проверяется RBAC), исполнитель — только активный пользователь с ролью `executor` (проверяется сервисом).

**attachments.** Файл хранится в MinIO под ключом `documents/<document_id>/<uuid>.<ext>`. Исходное имя сохраняется только для отображения и в `Content-Disposition` при скачивании.

**document_history.** Журнал действий по карточке. Запись создается в той же транзакции, что и само действие. Через API история доступна только для чтения. Коды действий: `document_registered`, `document_updated` (в `metadata.changes` — старое и новое значение каждого поля), `status_changed`, `document_annulled`, `resolution_created`, `resolution_updated`, `resolution_executed`, `file_attached`.

**Удаление карточки** (только администратор) каскадно удаляет ее резолюции, вложения и историю (`ON DELETE CASCADE`), затем объекты удаляются из MinIO. Факт удаления фиксируется в журнале приложения (stdout).

## Индексы

| Таблица | Индекс |
|---|---|
| incoming_documents | `registration_number` (UNIQUE), `received_date`, `registration_date`, `correspondent_id`, `document_type_id`, `execution_deadline`, `status`, `created_by`, GIN `pg_trgm` по `summary` |
| resolutions | `document_id`, `assigned_executor_id`, `status` |
| users | `login` (UNIQUE), `email` (UNIQUE), `role`, `department_id` |
| correspondents | `name`, `inn` |
| attachments | `document_id`, `storage_key` (UNIQUE) |
| document_history | `document_id`, `seq` (UNIQUE) |

Значения перечислений (роли, статусы, типы вложений) хранятся как `VARCHAR` с ограничением `CHECK`, без нативного `ENUM` PostgreSQL. Так новые значения добавляются обычной миграцией без `ALTER TYPE`.
