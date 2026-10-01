# Тест-кейсы и результаты

Всего **82 тестовые функции**:
- **32 unit-функции** (66 случаев с учетом параметризации) проверяют чистую доменную логику;
- **50 интеграционных функций** (52 случая) работают через REST API (httpx + ASGI) с настоящими PostgreSQL и MinIO; одна из них (`test_ui_static.py`) проверяет раздачу веб-интерфейса.

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
| Интеграционные тесты (`tests/integration`, 52 случая) | требуют Docker (PostgreSQL + MinIO) | **не запускались в среде разработки** (нет Docker и сети для установки зависимостей). Запускаются командой `docker compose --profile test run --rm tests` |

Дополнительно в среде разработки проверено:

- компиляция всех модулей;
- статический анализ: нет неиспользуемых импортов, неопределенных имен и импортов несуществующих объектов между модулями;
- сверка ER-диаграммы с миграцией и ORM-моделями (10 таблиц, столбцы совпадают);
- мутационная проверка теста диаграммы состояний: искаженная диаграмма дает падение теста;
- визуальная проверка PDF-отчета: кириллица отображается корректно.

После прогона в Docker эту таблицу нужно дополнить фактическим выводом pytest.

## Веб-интерфейс

Сценарии проверки (каждый выполняется под своей ролью):

| № | Сценарий | Ожидаемый результат |
|---|---|---|
| UI-01 | Вход с пустыми полями, с неверным паролем, верными данными | подсветка полей; «Неверный логин или пароль»; в `localStorage` только JWT |
| UI-02 | Меню каждой из четырех ролей | соответствует разрешениям из `/auth/me` |
| UI-03 | Журнал: пагинация, сортировка, фильтры, пустой результат | корректные строки; «По заданным условиям документов нет» |
| UI-04 | Подсветка сроков | просроченные — класс `is-overdue` и текст «просрочен на N», близкие — `is-warning` и «срок близок» |
| UI-05 | Регистрация: пустая форма, `page_count = 0`, срок раньше регистрации | ошибки у полей до отправки |
| UI-06 | Регистрация с датой поступления в будущем | ответ 422 сервера показан у поля `received_date` |
| UI-07 | Регистрация и «Прикрепить скан» | номер `ВХ-ГГГГ-NNNNNN` в штампе, файл загружен |
| UI-08 | Скачивание вложения | имя файла с кириллицей из `filename*`, содержимое совпадает побайтно |
| UI-09 | Редактирование реквизитов, история | запись «Количество листов: 3 → 5» |
| UI-10 | Резолюция на «зарегистрированном» документе | 409, уведомление с `detail` |
| UI-11 | Резолюция на документе «на рассмотрении», изменение резолюции | статус «на исполнении», автор, исполнитель, срок |
| UI-12 | Исполнитель: список, неверный тип файла, файл больше 20 МБ, отчет, отметка исполнения | только свои поручения; ошибки у поля; «исполнен» |
| UI-13 | Исполнитель открывает чужой документ, раздел `#/users`, несуществующий документ | «Нет доступа» + «Повторить»; «Нет доступа»; «Не найдено» |
| UI-14 | Снять с контроля → в архив (отмена и подтверждение) | отмена не меняет статус; в архиве редактирование и загрузка скрыты |
| UI-15 | Корреспонденты: неверные ИНН и email, создание, редактирование | ошибки у полей; запись в таблице |
| UI-16 | PDF-отчеты, CSV из раздела отчетов и из журнала | файлы `.pdf` (`%PDF`) и `.csv` (UTF-8 BOM) |
| UI-17 | Истекший токен | форма входа «Сессия завершена…», токен удален; после входа — тот же раздел |
| UI-18 | Администратор: пользователь (409 на занятый логин, создание, изменение, деактивация), попытка снять с себя роль | подсветка `login` и `role`; статус «деактивирован» |
| UI-19 | Справочники: добавление, дубликат, переименование, вывод типа из использования | 409 у поля; изменения в таблице |
| UI-20 | Администратор: открытие по номеру, аннулирование, удаление карточки | 404 для неизвестного номера; «зарегистрирован»; карточка больше не находится |
| UI-21 | Вход деактивированного пользователя | сообщение о деактивации |

**Как проверено.** В среде разработки нет Docker, поэтому интерфейс прогонялся в браузере Chromium (Playwright, окно 1280×860) против тестового эмулятора API. Эмулятор воспроизводит контракт backend: пути, схемы ответов, матрицу прав, переходы статусов и формат ошибок. В поставку он не входит. Результат: **83 проверки по сценариям UI-01…UI-21 пройдены**, исключений JavaScript нет. В консоли браузера были только сетевые записи об ответах 401/403/404/409/422, которые сценарии вызывали намеренно. Таблицы на 1280 и 1000 пикселях не требуют горизонтальной прокрутки.

Против настоящего backend (PostgreSQL + MinIO) интерфейс в среде разработки **не запускался**; `test_ui_static.py` тоже не запускался. После `docker compose up -d` и seed сценарии UI-01…UI-21 нужно пройти вручную по адресу http://localhost:8000/ui.
