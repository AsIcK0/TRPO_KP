# Тест-кейсы и результаты

Всего **81 тестовая функция**:
- **32 unit-функции** (66 случаев с учетом параметризации) проверяют чистую доменную логику;
- **49 интеграционных функций** (51 случай) работают через REST API (httpx + ASGI) с настоящими PostgreSQL и MinIO.

Запуск всех тестов:

```bash
docker compose --profile test run --rm tests            # все тесты
docker compose --profile test run --rm tests python -m pytest tests/unit -q   # только unit
```

## Соответствие обязательным сценариям (раздел 20 ТЗ)

| № | Сценарий из ТЗ | Тест (файл::функция) | Ожидаемый результат |
|---|---|---|---|
| TC-01 | Успешный вход | `integration/test_auth.py::test_login_success_returns_token_and_role` | 200, JWT, роль `clerk`, нет `password_hash` |
| TC-02 | Неверный пароль | `integration/test_auth.py::test_wrong_password_and_unknown_login_return_401` | 401 `INVALID_CREDENTIALS` (и для несуществующего логина) |
| TC-03 | Деактивированный пользователь не входит | `integration/test_auth.py::test_deactivated_user_cannot_login_nor_use_old_token` | 403 `USER_INACTIVE` при входе и со старым токеном |
| TC-04 | Создание пользователя администратором | `integration/test_users_and_dictionaries.py::test_admin_creates_user_without_exposing_password_hash` | 201, вход новым паролем, 409 на дубль логина/email |
| TC-05 | Создание корреспондента | `integration/test_correspondents.py::test_clerk_creates_edits_and_finds_correspondent` | 201, редактирование, поиск |
| TC-06 | Регистрация документа и получение номера | `integration/test_documents.py::test_register_document_assigns_number_date_and_history` | 201, `ВХ-<год>-000001`, затем `…000002`, дата регистрации, запись истории |
| TC-07 | Отклонение `execution_deadline < registration_date` | `integration/test_documents.py::test_deadline_before_registration_is_rejected` | 422 `VALIDATION_ERROR`, `field = execution_deadline` |
| TC-08 | Создание резолюции руководителем | `integration/test_resolutions_workflow.py::test_manager_creates_resolution_and_document_goes_to_execution` | 201, документ «на исполнении», история |
| TC-09 | Просмотр поручения исполнителем | `integration/test_resolutions_workflow.py::test_executor_sees_only_own_assignments` | свои документы видны, чужие — 403 |
| TC-10 | Прикрепление отчета | `integration/test_resolutions_workflow.py::test_executor_attaches_report_and_marks_execution` | 201, тип `execution_report` |
| TC-11 | Отметка исполнения | там же + `test_document_executed_only_when_all_executors_done` | «исполнен», когда закрыты все резолюции; повтор — 409 |
| TC-12 | Смена статуса и запись в историю | `integration/test_documents.py::test_status_change_is_written_to_history` | old/new status, автор, время, комментарий |
| TC-13 | Поиск по номеру | `integration/test_search.py::test_search_by_registration_number` | частичный номер, точный эндпоинт, 404 |
| TC-14 | Поиск по корреспонденту | `integration/test_search.py::test_search_by_correspondent_status_type_and_executor` | только документы корреспондента |
| TC-15 | Фильтр по статусу | там же | только «на исполнении» |
| TC-16 | Фильтр по датам | `integration/test_search.py::test_filter_by_dates` | диапазоны; `date_from > date_to` — 422 |
| TC-17 | CSV с кириллицей | `integration/test_reports_exports.py::test_csv_registration_log_with_cyrillic` | BOM, `;`, русские заголовки, данные = БД |
| TC-18 | PDF-отчет | `integration/test_reports_exports.py::test_pdf_reports_are_generated[documents/executors/deadlines]` | 200 `application/pdf` для всех трех типов |
| TC-19 | Запрет редактирования архивного документа | `integration/test_documents.py::test_archived_document_cannot_be_edited` | 409 `DOCUMENT_ARCHIVED` (редактирование и загрузка файла) |
| TC-20 | Запрет удаления документа не-администратором | `integration/test_documents.py::test_only_admin_can_delete_document` | 403 для clerk/manager/executor, 204 для admin, каскад |
| TC-21 | 403 при недопустимой роли | `…::test_non_admin_cannot_manage_users`, `…::test_correspondent_validation_and_rbac`, `…::test_only_clerk_registers_and_edits`, `…::test_csv_filters_and_rbac` и др. | 403 `FORBIDDEN` в едином формате ошибки |
| TC-22 | Запрет скачивания файла без прав | `integration/test_files.py::test_download_forbidden_without_rights` | без токена 401, чужой исполнитель 403 |

## Дополнительные проверки сверх обязательных

| Область | Тест | Что проверяет |
|---|---|---|
| Гонки при регистрации | `test_documents.py::test_parallel_registration_produces_unique_numbers` | 12 параллельных регистраций: номера уникальны, без пропусков |
| Целостность | `test_documents.py::test_registration_integrity_checks` | `page_count ≥ 1`, существующие корреспондент и тип, неактивный тип, дата поступления |
| Недопустимый переход | `test_documents.py::test_invalid_transition_returns_409_and_role_check_returns_403` | 409 для несуществующего перехода, 403 для чужой роли, в историю не пишется |
| История только для чтения | `test_documents.py::test_history_is_read_only` | POST/PUT/PATCH/DELETE — 405 |
| Аннулирование | `test_documents.py::test_admin_annuls_document_back_to_registered` | из архива в «зарегистрирован», `archived_at` сброшен |
| Роль из БД | `test_auth.py::test_role_is_always_loaded_from_db` | смена роли действует на уже выданный токен |
| Резолюции | `test_resolutions_workflow.py::test_resolution_rules`, `::test_resolution_editable_until_completion` | состояние документа, только manager, только активный executor, блокировка после исполнения |
| Полный цикл | `test_resolutions_workflow.py::test_full_lifecycle_to_archive` | все 6 статусов в истории по порядку |
| Файлы | `test_files.py::test_clerk_uploads_scan_to_s3_and_downloads_it`, `::test_storage_key_is_server_generated`, `::test_invalid_uploads_are_rejected` | объект в MinIO, побайтное совпадение, ключ без исходного имени, path traversal, MIME/сигнатура/размер (413) |
| Контроль сроков | `test_search.py::test_deadline_control_overdue_and_warning` | `overdue`/`warning`/`ok`, `days_left`, фильтр `deadline_state` |
| Поиск | `test_search.py::test_keyword_search_…`, `::test_pagination_and_sorting` | регистронезависимый кириллический поиск, экранирование `%_`, пагинация, сортировка, 422 на недопустимое поле |
| Отчеты | `test_reports_exports.py::test_pdf_report_with_filters_and_validation` | фильтры, обязательный период, 403 для executor/admin |
| Seed | `test_seed.py::test_seed_creates_consistent_demo_data` | состав данных, все статусы, история соответствует статусам, идемпотентность, вход тестовыми учетками |
| Инфраструктура | `test_health_openapi.py` | `/health` (БД+S3), Swagger, наличие всех эндпоинтов раздела 11 в OpenAPI |
| Документация = код | `unit/test_docs_consistency.py`, `integration/test_docs_schema.py` | диаграмма состояний и ER-диаграмма совпадают с кодом |
| Unit | `tests/unit/*` | номер по шаблону, переходы, сроки, RBAC-матрица, JWT, проверка файлов, CSV, показатели отчетов, PDF с кириллицей |

## Результаты прогона

| Набор | Где выполнен | Результат |
|---|---|---|
| Unit-тесты (`tests/unit`, 66 случаев) | среда разработки: Python 3.12, без доступа к сети, запуск через минимальный совместимый раннер | **66 / 66 пройдено** |
| Интеграционные тесты (`tests/integration`, 51 случай) | требуют Docker (PostgreSQL + MinIO) | **не запускались в среде разработки** (нет Docker и сети для установки зависимостей). Запускаются командой `docker compose --profile test run --rm tests` |

Дополнительно в среде разработки проверено:

- компиляция всех модулей;
- статический анализ: нет неиспользуемых импортов, неопределенных имен и импортов несуществующих объектов между модулями;
- сверка ER-диаграммы с миграцией и ORM-моделями (10 таблиц, столбцы совпадают);
- мутационная проверка теста диаграммы состояний: искаженная диаграмма дает падение теста;
- визуальная проверка PDF-отчета: кириллица отображается корректно.

После прогона в Docker эту таблицу нужно дополнить фактическим выводом pytest.
