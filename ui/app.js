/**
 * Веб-интерфейс системы учета входящей корреспонденции.
 * Vanilla JS (ES-модули), без сборки. Работает только с реальным REST API (/api/v1).
 *
 * Разграничение доступа в интерфейсе строится по разрешениям из GET /auth/me и служит
 * только удобству: кнопки, недоступные роли, скрыты. Настоящая проверка прав — на backend.
 */

import { api, ApiError, auth, saveBlob } from "/ui/api.js";

/* ==========================================================================
   Подписи и справочные значения для отображения
   ========================================================================== */

const APP_NAME = "Учёт входящей корреспонденции";

const ROLE_LABELS = {
  clerk: "Делопроизводитель",
  manager: "Руководитель",
  executor: "Исполнитель",
  admin: "Администратор",
};

const STATUSES = ["зарегистрирован", "на рассмотрении", "на исполнении", "исполнен", "снят с контроля", "в архиве"];
const STATUS_CLASS = {
  "зарегистрирован": "status-registered",
  "на рассмотрении": "status-review",
  "на исполнении": "status-execution",
  "исполнен": "status-executed",
  "снят с контроля": "status-removed",
  "в архиве": "status-archived",
};
const ARCHIVED = "в архиве";

const ATTACHMENT_TYPES = {
  source_scan: "Скан документа",
  execution_report: "Отчёт об исполнении",
  other: "Прочее",
};

const HISTORY_ACTIONS = {
  document_registered: "Регистрация",
  document_updated: "Изменение реквизитов",
  status_changed: "Смена статуса",
  document_annulled: "Аннулирование",
  resolution_created: "Резолюция создана",
  resolution_updated: "Резолюция изменена",
  resolution_executed: "Резолюция исполнена",
  file_attached: "Файл прикреплён",
};

const FIELD_LABELS = {
  received_date: "Дата поступления",
  correspondent_id: "Корреспондент",
  addressee: "Адресат",
  summary: "Краткое содержание",
  document_type_id: "Тип документа",
  page_count: "Количество листов",
  execution_deadline: "Срок исполнения",
  text: "Текст резолюции",
  assigned_executor_id: "Исполнитель",
  deadline: "Срок",
};

const REPORT_TYPES = [
  { value: "documents", title: "По документам", text: "Документы за период: реквизиты, статус, исполнители, просрочка." },
  { value: "executors", title: "По исполнителям", text: "Количество поручений, средний срок исполнения и доля просрочки." },
  { value: "deadlines", title: "По срокам исполнения", text: "Исполненные в срок, с опозданием и просроченные, отклонение в днях." },
];

/*
 * Какие кнопки смены статуса показывать роли. Это только подсказка интерфейса:
 * допустимость перехода и права проверяет backend (409 / 403 при нарушении).
 */
const STATUS_BUTTONS = {
  clerk: [
    { from: "зарегистрирован", to: "на рассмотрении", label: "Передать на рассмотрение" },
    { from: "исполнен", to: "снят с контроля", label: "Снять с контроля" },
    { from: "снят с контроля", to: "в архиве", label: "Передать в архив", confirm: true },
  ],
  executor: [{ from: "на исполнении", to: "исполнен", label: "Отметить исполнение" }],
};

/* Ограничения на файлы (дублируют серверные для быстрой обратной связи; решает сервер). */
const FILE_MAX_BYTES = 20 * 1024 * 1024;
const FILE_EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png", ".docx"];
const FILE_ACCEPT = FILE_EXTENSIONS.join(",");

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/* ==========================================================================
   Сессия и права
   ========================================================================== */

const session = { me: null, perms: new Set() };
const can = (permission) => session.perms.has(permission);
const role = () => session.me?.role;
const canListExecutors = () => can("resolution:create") || can("user:view");

/* Кэш справочников для выпадающих списков (промисы, чтобы не дублировать запросы). */
const cache = {};
function cached(key, loader) {
  if (!cache[key]) {
    cache[key] = loader().catch((error) => {
      delete cache[key];
      throw error;
    });
  }
  return cache[key];
}
const dropCache = (...keys) => keys.forEach((key) => delete cache[key]);

/* Имена по идентификаторам — для расшифровки изменений в истории карточки. */
const names = new Map();
function remember(items, label = (item) => item.name ?? item.full_name) {
  for (const item of items) names.set(String(item.id), label(item));
  return items;
}
const loadTypes = () => cached("types", () => api.documentTypes.list().then((items) => remember(items)));
const loadCorrespondents = () => cached("correspondents", () => api.correspondents.all().then((items) => remember(items)));
const loadExecutors = () => cached("executors", () => api.users.executors().then((items) => remember(items)));
const loadDepartments = () => cached("departments", () => api.departments.list());
const loadPositions = () => cached("positions", () => api.positions.list());

/* ==========================================================================
   DOM-утилиты (все данные выводятся как текст — без innerHTML)
   ========================================================================== */

const $ = (selector, root = document) => root.querySelector(selector);

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (key === "value" && (tag === "input" || tag === "textarea")) el.value = value;
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, String(value));
  }
  append(el, children);
  return el;
}

function append(el, ...children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : String(child));
  }
  return el;
}

let uid = 0;
const nextId = (prefix = "f") => `${prefix}-${++uid}`;

/* ==========================================================================
   Форматирование
   ========================================================================== */

const pad = (n) => String(n).padStart(2, "0");

function isoDate(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
const todayISO = () => isoDate(new Date());

function fmtDate(value) {
  if (!value) return "—";
  const [y, m, d] = String(value).slice(0, 10).split("-");
  return d && m && y ? `${d}.${m}.${y}` : String(value);
}

function fmtDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("ru-RU", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
}

function plural(n, one, few, many) {
  const abs = Math.abs(n) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return many;
  if (last === 1) return one;
  if (last >= 2 && last <= 4) return few;
  return many;
}

const days = (n) => `${n} ${plural(n, "день", "дня", "дней")}`;

/* ==========================================================================
   Небольшие компоненты
   ========================================================================== */

function statusBadge(status) {
  return h("span", { class: `status ${STATUS_CLASS[status] || "status-registered"}` }, status);
}

/** Текстовая пометка о сроке: цвет дублируется словами. Состояние считает backend. */
function deadlineInfo(doc) {
  const n = Math.abs(doc.days_left ?? 0);
  switch (doc.deadline_state) {
    case "overdue":
      return { cls: "overdue", text: `просрочен на ${days(n)}` };
    case "warning":
      return { cls: "warning", text: n === 0 ? "срок сегодня" : `срок близок: осталось ${days(n)}` };
    case "closed":
      return { cls: "closed", text: "контроль завершён" };
    default:
      return { cls: "ok", text: doc.days_left != null ? `осталось ${days(n)}` : "" };
  }
}

function stamp(doc) {
  return h(
    "div",
    { class: "stamp", "aria-label": `Входящий номер ${doc.registration_number} от ${fmtDate(doc.registration_date)}` },
    h("div", { class: "stamp-caption" }, "Вх. №"),
    h("div", { class: "stamp-number" }, doc.registration_number),
    h("div", { class: "stamp-date" }, `от ${fmtDate(doc.registration_date)}`),
  );
}

function loadingBox(text = "Загрузка…") {
  return h("div", { class: "state-box", role: "status" }, h("div", { class: "spinner" }), text);
}

function emptyBox(text = "Нет данных", action) {
  return h("div", { class: "state-box" }, h("div", {}, text), action);
}

function errorBox(error, retry) {
  const message = error instanceof ApiError ? error.detail || `Ошибка ${error.status}` : "Не удалось загрузить данные";
  return h(
    "div",
    { class: "state-box error", role: "alert" },
    h("div", {}, message),
    retry && h("button", { class: "btn", type: "button", onclick: retry }, "Повторить"),
  );
}

function pageHead(title, subtitle, ...rawActions) {
  document.title = `${title} — ${APP_NAME}`;
  const actions = rawActions.filter(Boolean);
  return h(
    "div",
    { class: "page-head" },
    h("div", { class: "titles" }, h("h1", {}, title), subtitle && h("p", {}, subtitle)),
    actions.length ? h("div", { class: "actions" }, actions) : null,
  );
}

function pager(data, onPage, onSize) {
  const from = data.total === 0 ? 0 : (data.page - 1) * data.page_size + 1;
  const to = Math.min(data.page * data.page_size, data.total);
  const size = h(
    "select",
    { "aria-label": "Записей на странице", onchange: (e) => onSize(Number(e.target.value)) },
    [20, 50, 100].map((n) => h("option", { value: n, selected: n === data.page_size }, `${n} на странице`)),
  );
  return h(
    "div",
    { class: "pager" },
    h("span", { class: "spacer" }, data.total ? `Записи ${from}–${to} из ${data.total}` : "Записей нет"),
    size,
    h("button", { class: "btn btn-sm", type: "button", disabled: data.page <= 1, onclick: () => onPage(data.page - 1) }, "Назад"),
    h("span", {}, `Стр. ${data.pages ? data.page : 0} из ${data.pages}`),
    h("button", { class: "btn btn-sm", type: "button", disabled: data.page >= data.pages, onclick: () => onPage(data.page + 1) }, "Вперёд"),
  );
}

/* ==========================================================================
   Уведомления и диалоги
   ========================================================================== */

function toast(message, { type = "info", title } = {}) {
  const box = $("#toasts");
  const el = h(
    "div",
    { class: `toast ${type}`, role: type === "error" ? "alert" : "status" },
    h("div", { class: "toast-body" }, title && h("div", { class: "toast-title" }, title), message && h("div", {}, message)),
    h("button", { type: "button", "aria-label": "Закрыть уведомление", onclick: () => el.remove() }, "×"),
  );
  box.append(el);
  setTimeout(() => el.remove(), type === "error" || type === "warn" ? 7000 : 4000);
}

const openModals = new Set();

function closeAllModals() {
  for (const close of [...openModals]) close();
}

/** Модальное окно. Возвращает функцию закрытия. */
function openModal({ title, body, actions = [], danger = false, onClose }) {
  const root = $("#modal-root");
  const returnFocus = document.activeElement;
  const titleId = nextId("modal-title");
  let closed = false;

  const onKey = (event) => {
    if (event.key === "Escape") close();
  };
  const close = () => {
    if (closed) return;
    closed = true;
    openModals.delete(close);
    backdrop.remove();
    document.removeEventListener("keydown", onKey);
    if (returnFocus && returnFocus.isConnected) returnFocus.focus();
    onClose?.();
  };
  const backdrop = h(
    "div",
    { class: "modal-backdrop", onmousedown: (event) => event.target === backdrop && close() },
    h(
      "div",
      { class: `modal${danger ? " danger" : ""}`, role: "dialog", "aria-modal": "true", "aria-labelledby": titleId },
      h(
        "div",
        { class: "modal-head" },
        h("h2", { id: titleId }, title),
        h("button", { class: "modal-close", type: "button", "aria-label": "Закрыть", onclick: close }, "×"),
      ),
      h("div", { class: "modal-body" }, body),
      actions.length ? h("div", { class: "modal-foot" }, actions) : null,
    ),
  );
  root.append(backdrop);
  openModals.add(close);
  document.addEventListener("keydown", onKey);
  const focusTarget = backdrop.querySelector("input:not([type=hidden]), select, textarea, .modal-foot .btn-primary, .modal-foot .btn");
  (focusTarget || backdrop.querySelector(".modal-close")).focus();
  return close;
}

function confirmDialog({ title, message, confirmText = "Подтвердить", danger = true }) {
  return new Promise((resolve) => {
    let confirmed = false;
    const close = openModal({
      title,
      danger,
      body: h("p", { style: "margin: 0 0 4px" }, message),
      onClose: () => resolve(confirmed),
      actions: [
        h("button", { class: "btn", type: "button", onclick: () => close() }, "Отмена"),
        h(
          "button",
          {
            class: danger ? "btn btn-danger-solid" : "btn btn-primary",
            type: "button",
            onclick: () => {
              confirmed = true;
              close();
            },
          },
          confirmText,
        ),
      ],
    });
  });
}

/* ==========================================================================
   Ошибки API
   ========================================================================== */

/** Текст ошибки для вывода рядом с полем: без префикса «имя_поля: ». */
function fieldMessage(error) {
  const detail = error.detail || "Недопустимое значение";
  return error.field && detail.startsWith(`${error.field}: `) ? detail.slice(error.field.length + 2) : detail;
}

/**
 * Единая обработка ошибок API.
 * 401 — уже обработан клиентом (показана форма входа); 403 — «Нет доступа»; 404 — «Не найдено»;
 * 409 — сообщение сервера; 413 — «Файл слишком большой»; 422 — подсветка поля из `field`.
 */
function handleError(error, { form } = {}) {
  if (!(error instanceof ApiError)) {
    console.error(error);
    toast("Обновите страницу и повторите действие.", { type: "error", title: "Ошибка интерфейса" });
    return;
  }
  switch (error.status) {
    case 401:
      return;
    case 403:
      if (error.code === "USER_INACTIVE") {
        auth.clear();
        showLogin("Учётная запись деактивирована. Обратитесь к администратору.");
        return;
      }
      toast(error.detail, { type: "error", title: "Нет доступа" });
      return;
    case 404:
      toast(error.detail, { type: "error", title: "Не найдено" });
      return;
    case 409:
      if (form && error.field) showFieldError(form, error.field, fieldMessage(error));
      toast(error.detail, { type: "warn", title: "Действие отклонено" });
      return;
    case 413:
      if (form) showFieldError(form, "file", error.detail || "Файл слишком большой");
      toast(error.detail, { type: "error", title: "Файл слишком большой" });
      return;
    case 422:
      if (form && error.field && showFieldError(form, error.field, fieldMessage(error))) return;
      toast(error.detail, { type: "error", title: "Ошибка в данных" });
      return;
    case 0:
      toast(error.detail, { type: "error", title: "Нет связи с сервером" });
      return;
    default:
      toast(error.detail || "Повторите попытку позже.", { type: "error", title: `Ошибка сервера (${error.status})` });
  }
}

/* ==========================================================================
   Формы и валидация
   ========================================================================== */

/**
 * Поле формы: подпись, элемент ввода, подсказка и место для ошибки.
 * type: text | email | password | number | date | textarea | select | file
 */
function field({ label, name, type = "text", required = false, value, hint, options, placeholder, attrs = {}, span2 = false }) {
  const id = nextId(name);
  let control;
  if (type === "textarea") {
    control = h("textarea", { id, name, required, ...attrs });
    if (value != null) control.value = value;
  } else if (type === "select") {
    control = h(
      "select",
      { id, name, required, ...attrs },
      placeholder !== undefined && h("option", { value: "" }, placeholder),
      (options || []).map((o) => h("option", { value: o.value, selected: value != null && String(o.value) === String(value) }, o.label)),
    );
  } else {
    control = h("input", { id, name, type, required, ...attrs });
    if (value != null && type !== "file") control.value = value;
  }
  return h(
    "div",
    { class: `field${span2 ? " span-2" : ""}` },
    h("label", { for: id }, label, required && h("span", { class: "req", "aria-hidden": "true" }, "*")),
    control,
    hint && h("div", { class: "hint" }, hint),
    h("div", { class: "field-error", id: `${id}-error` }),
  );
}

function showFieldError(form, name, message) {
  const input = form.querySelector(`[name="${CSS.escape(name)}"]`);
  const wrap = input?.closest(".field");
  if (!input || !wrap) return false;
  wrap.classList.add("has-error");
  input.setAttribute("aria-invalid", "true");
  const box = wrap.querySelector(".field-error");
  if (box) {
    box.textContent = message;
    input.setAttribute("aria-describedby", box.id);
  }
  input.focus();
  return true;
}

function clearFieldErrors(form) {
  form.querySelectorAll(".field.has-error").forEach((wrap) => wrap.classList.remove("has-error"));
  form.querySelectorAll("[aria-invalid]").forEach((el) => el.removeAttribute("aria-invalid"));
  form.querySelectorAll(".field-error").forEach((box) => (box.textContent = ""));
}

function checkFile(file) {
  if (!file) return null;
  const name = file.name.toLowerCase();
  if (!FILE_EXTENSIONS.some((ext) => name.endsWith(ext))) return "Допустимые форматы: PDF, JPG, PNG, DOCX";
  if (file.size === 0) return "Файл пустой";
  if (file.size > FILE_MAX_BYTES) return "Размер файла больше 20 МБ";
  return null;
}

/**
 * Проверки формы перед отправкой: обязательные поля, email, минимумы чисел и дат, шаблоны,
 * файлы и дополнительные проверки `extra` вида [[имя_поля, () => сообщение | null], ...].
 * Окончательную проверку всегда выполняет сервер.
 */
function validateForm(form, extra = []) {
  clearFieldErrors(form);
  const errors = new Map();
  const add = (name, message) => {
    if (name && message && !errors.has(name)) errors.set(name, message);
  };
  for (const el of form.elements) {
    if (!el.name || el.disabled) continue;
    const value = el.type === "file" ? null : String(el.value).trim();
    if (el.required && (el.type === "file" ? !el.files.length : !value)) add(el.name, "Заполните поле");
    else if (el.type === "email" && value && !EMAIL_RE.test(value)) add(el.name, "Неверный формат email");
    else if (el.type === "number" && value && el.min !== "" && Number(value) < Number(el.min)) add(el.name, `Не меньше ${el.min}`);
    else if (el.type === "date" && value && el.min && value < el.min) add(el.name, `Не раньше ${fmtDate(el.min)}`);
    else if (el.pattern && value && !new RegExp(`^(?:${el.pattern})$`).test(value)) add(el.name, el.title || "Неверный формат");
    else if (el.type !== "file" && el.minLength > 0 && value && value.length < el.minLength) add(el.name, `Не короче ${el.minLength} символов`);
    else if (el.type === "file" && el.files.length) add(el.name, checkFile(el.files[0]));
  }
  for (const [name, check] of extra) add(name, check());
  let first = true;
  for (const [name, message] of errors) {
    showFieldError(form, name, message);
    if (first) {
      form.querySelector(`[name="${CSS.escape(name)}"]`)?.focus();
      first = false;
    }
  }
  return errors.size === 0;
}

/** Значения полей формы; пустые строки превращаются в null. */
function formValues(form) {
  const values = {};
  for (const el of form.elements) {
    if (!el.name || el.type === "file" || el.type === "submit" || el.type === "button") continue;
    if (el.type === "radio" && !el.checked) continue;
    const value = String(el.value).trim();
    values[el.name] = value === "" ? null : value;
  }
  return values;
}

/** Выполнить действие с индикатором на кнопке. */
async function withBusy(button, action) {
  if (button) {
    button.disabled = true;
    button.classList.add("is-busy");
  }
  try {
    return await action();
  } finally {
    if (button && button.isConnected) {
      button.disabled = false;
      button.classList.remove("is-busy");
    }
  }
}

/**
 * Загрузка данных в контейнер: индикатор, ошибка с кнопкой «Повторить».
 * render получает данные и должен заполнить контейнер.
 */
async function loadInto(container, loader, render) {
  container.replaceChildren(loadingBox());
  try {
    const data = await loader();
    if (container.isConnected) render(data);
  } catch (error) {
    if (!container.isConnected) return;
    if (error instanceof ApiError && error.status === 401) return;
    handleError(error);
    container.replaceChildren(errorBox(error, () => loadInto(container, loader, render)));
  }
}

const optionList = (items, label = (item) => item.name) => items.map((item) => ({ value: item.id, label: label(item) }));
const statusOptions = () => STATUSES.map((s) => ({ value: s, label: s }));

/* ==========================================================================
   Навигация
   ========================================================================== */

function documentsLabel() {
  if (can("document:search")) return "Журнал документов";
  if (role() === "executor") return "Мои поручения";
  return "Документы";
}

const NAV = [
  { key: "documents", href: "#/documents", label: documentsLabel, visible: () => can("document:view") },
  { key: "register", href: "#/documents/new", label: () => "Регистрация документа", visible: () => can("document:register") },
  { key: "correspondents", href: "#/correspondents", label: () => "Корреспонденты", visible: () => can("correspondent:view") },
  {
    key: "reports",
    href: "#/reports",
    label: () => (can("report:generate") && can("export:registry") ? "Отчёты и выгрузка" : can("report:generate") ? "Отчёты" : "Выгрузка журнала"),
    visible: () => can("report:generate") || can("export:registry"),
  },
  { group: "Администрирование", visible: () => can("user:view") || can("dictionary:manage") },
  { key: "users", href: "#/users", label: () => "Пользователи", visible: () => can("user:view") },
  { key: "dictionaries", href: "#/dictionaries", label: () => "Справочники", visible: () => can("dictionary:manage") },
];

function renderNav(activeKey) {
  const nav = $("#sidenav");
  nav.replaceChildren(
    ...NAV.filter((item) => item.visible()).map((item) =>
      item.group
        ? h("div", { class: "nav-group" }, item.group)
        : h("a", { href: item.href, "aria-current": item.key === activeKey ? "page" : null }, item.label()),
    ),
  );
}

const ROUTES = [
  { pattern: /^\/documents\/new$/, view: (c, ctx) => viewRegister(c, ctx), allowed: () => can("document:register"), nav: "register" },
  { pattern: /^\/documents\/([0-9a-fA-F-]{36})$/, view: (c, ctx) => viewCard(c, ctx), allowed: () => can("document:view"), nav: "documents" },
  { pattern: /^\/documents$/, view: (c, ctx) => viewDocuments(c, ctx), allowed: () => can("document:view"), nav: "documents" },
  { pattern: /^\/correspondents$/, view: (c, ctx) => viewCorrespondents(c, ctx), allowed: () => can("correspondent:view"), nav: "correspondents" },
  { pattern: /^\/reports$/, view: (c, ctx) => viewReports(c, ctx), allowed: () => can("report:generate") || can("export:registry"), nav: "reports" },
  { pattern: /^\/users$/, view: (c, ctx) => viewUsers(c, ctx), allowed: () => can("user:view"), nav: "users" },
  { pattern: /^\/dictionaries$/, view: (c, ctx) => viewDictionaries(c, ctx), allowed: () => can("dictionary:manage"), nav: "dictionaries" },
];

function defaultPath() {
  if (role() === "admin") return "/users";
  if (can("document:view")) return "/documents";
  return "/reports";
}

function parseHash() {
  const raw = window.location.hash.replace(/^#/, "") || "/";
  const [path, query] = raw.split("?");
  return { path: path || "/", params: new URLSearchParams(query || "") };
}

const navigate = (path) => {
  window.location.hash = `#${path}`;
};

let renderToken = 0;

async function router() {
  if (!session.me) return;
  const { path, params } = parseHash();
  if (path === "/") {
    navigate(defaultPath());
    return;
  }
  closeAllModals();
  const content = $("#content");
  const route = ROUTES.find((r) => r.pattern.test(path));
  renderNav(route?.nav);
  window.scrollTo(0, 0);

  if (!route) {
    document.title = APP_NAME;
    content.replaceChildren(pageHead("Страница не найдена"), emptyBox("Такого раздела нет.", h("a", { class: "btn", href: `#${defaultPath()}` }, "На главную")));
    return;
  }
  if (!route.allowed()) {
    // Раздел скрыт для роли. Это удобство интерфейса; доступ все равно проверяет backend.
    toast("Раздел недоступен для вашей роли.", { type: "error", title: "Нет доступа" });
    content.replaceChildren(pageHead("Нет доступа"), emptyBox("Этот раздел недоступен для вашей роли.", h("a", { class: "btn", href: `#${defaultPath()}` }, "На главную")));
    return;
  }
  const token = ++renderToken;
  const id = path.match(route.pattern)[1];
  content.replaceChildren();
  await route.view(content, { id, params, isCurrent: () => token === renderToken });
}

/* ==========================================================================
   Вход, выход, запуск
   ========================================================================== */

function showLogin(message) {
  session.me = null;
  session.perms = new Set();
  for (const key of Object.keys(cache)) delete cache[key];
  names.clear();
  closeAllModals();
  $("#boot").hidden = true;
  $("#app-view").hidden = true;
  $("#login-view").hidden = false;
  document.title = `Вход — ${APP_NAME}`;
  const alert = $("#login-error");
  alert.hidden = !message;
  alert.textContent = message || "";
  const form = $("#login-form");
  form.password.value = "";
  (form.login.value ? form.password : form.login).focus();
}

async function startSession() {
  $("#boot").hidden = false;
  try {
    const me = await api.me();
    session.me = me;
    session.perms = new Set(me.permissions);
    $("#user-name").textContent = me.full_name;
    $("#user-role").textContent = ROLE_LABELS[me.role] || me.role;
    $("#boot").hidden = true;
    $("#login-view").hidden = true;
    $("#app-view").hidden = false;
    await router();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return; // уже показан вход
    if (error instanceof ApiError && error.code === "USER_INACTIVE") {
      auth.clear();
      showLogin("Учётная запись деактивирована. Обратитесь к администратору.");
      return;
    }
    $("#boot").replaceChildren(errorBox(error, () => window.location.reload()));
  }
}

async function onLoginSubmit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const alert = $("#login-error");
  alert.hidden = true;
  if (!validateForm(form)) return;
  const button = form.querySelector("button[type=submit]");
  await withBusy(button, async () => {
    try {
      const result = await api.login(form.login.value.trim(), form.password.value);
      auth.save(result.access_token);
      form.password.value = "";
      await startSession();
    } catch (error) {
      form.password.value = "";
      alert.hidden = false;
      if (error instanceof ApiError && error.status === 401) alert.textContent = "Неверный логин или пароль.";
      else if (error instanceof ApiError && error.code === "USER_INACTIVE") alert.textContent = "Учётная запись деактивирована. Обратитесь к администратору.";
      else alert.textContent = error.detail || "Не удалось выполнить вход.";
      form.password.focus();
    }
  });
}

function logout() {
  auth.clear();
  window.location.hash = "";
  showLogin();
}

function boot() {
  auth.onUnauthorized(() => showLogin("Сессия завершена или недействительна. Войдите снова."));
  $("#login-form").addEventListener("submit", onLoginSubmit);
  $("#logout-btn").addEventListener("click", logout);
  window.addEventListener("hashchange", router);
  if (auth.token) startSession();
  else showLogin();
}

/* ==========================================================================
   Журнал документов · Мои поручения · Документы (администратор)
   ========================================================================== */

const journal = { page: 1, page_size: 20, sort: "-registration_date", filters: {} };

const DOC_COLUMNS = [
  { title: "Рег. номер", sort: "registration_number" },
  { title: "Поступил", sort: "received_date" },
  { title: "Корреспондент" },
  { title: "Тип" },
  { title: "Содержание" },
  { title: "Исполнитель" },
  { title: "Срок", sort: "execution_deadline" },
  { title: "Статус", sort: "status" },
];

function rowClass(doc) {
  if (doc.deadline_state === "overdue") return "is-overdue";
  if (doc.deadline_state === "warning") return "is-warning";
  return null;
}

function documentsTable(items, sort, onSort) {
  const current = sort.split(",")[0];
  const key = current.replace(/^-/, "");
  const desc = current.startsWith("-");
  const head = DOC_COLUMNS.map((col) => {
    if (!col.sort) return h("th", { scope: "col" }, col.title);
    const active = col.sort === key;
    const next = active && !desc ? `-${col.sort}` : col.sort;
    return h(
      "th",
      { scope: "col", "aria-sort": active ? (desc ? "descending" : "ascending") : "none" },
      h(
        "button",
        { class: "sort-btn", type: "button", title: "Сортировать", onclick: () => onSort(next) },
        col.title,
        active && h("span", { class: "dir", "aria-hidden": "true" }, desc ? "▼" : "▲"),
      ),
    );
  });
  const rows = items.map((doc) => {
    const info = deadlineInfo(doc);
    return h(
      "tr",
      {
        class: rowClass(doc),
        style: "cursor: pointer",
        onclick: (event) => {
          if (!event.target.closest("a, button")) navigate(`/documents/${doc.id}`);
        },
      },
      h("td", {}, h("a", { class: "doc-number", href: `#/documents/${doc.id}` }, doc.registration_number)),
      h("td", { class: "nowrap" }, fmtDate(doc.received_date)),
      h("td", {}, doc.correspondent.name),
      h("td", {}, doc.document_type.name),
      h("td", { class: "summary-cell" }, h("span", { title: doc.summary }, doc.summary)),
      h("td", {}, doc.executors.length ? doc.executors.map((e) => e.full_name).join(", ") : h("span", { class: "muted" }, "не назначен")),
      h(
        "td",
        { class: "deadline-cell" },
        h("span", { class: "nowrap" }, fmtDate(doc.execution_deadline)),
        info.text && h("span", { class: `deadline-note ${info.cls}` }, info.text),
      ),
      h("td", {}, statusBadge(doc.status)),
    );
  });
  return h(
    "table",
    { class: "doc-table" },
    h("caption", { class: "sr-only" }, "Входящие документы"),
    h("thead", {}, h("tr", {}, head)),
    h("tbody", {}, rows),
  );
}

/** Заполнить выпадающий список, когда придут данные справочника. */
function fillSelect(select, promise, label = (item) => item.name, filter = () => true) {
  const selected = select.dataset.selected || "";
  promise
    .then((items) => {
      for (const item of items.filter(filter)) {
        select.append(h("option", { value: item.id, selected: String(item.id) === selected }, label(item)));
      }
    })
    .catch(() => {
      select.append(h("option", { value: "", disabled: true }, "Не удалось загрузить список"));
    });
}

function journalFilters(onApply) {
  const f = journal.filters;
  const typeField = field({ label: "Тип документа", name: "document_type_id", type: "select", placeholder: "Все типы" });
  const corrField = can("correspondent:view")
    ? field({ label: "Корреспондент", name: "correspondent_id", type: "select", placeholder: "Все корреспонденты" })
    : null;
  const execField = canListExecutors()
    ? field({ label: "Исполнитель", name: "executor_id", type: "select", placeholder: "Все исполнители" })
    : null;

  const form = h(
    "form",
    { class: "filters journal-filters", role: "search", novalidate: true },
    field({
      label: "Поиск",
      name: "search",
      type: "search",
      value: f.search,
      attrs: { placeholder: "Номер, содержание, адресат или корреспондент" },
    }),
    field({ label: "Статус", name: "status", type: "select", placeholder: "Все статусы", options: statusOptions(), value: f.status }),
    typeField,
    corrField,
    execField,
    field({ label: "Зарегистрированы с", name: "date_from", type: "date", value: f.date_from }),
    field({ label: "по", name: "date_to", type: "date", value: f.date_to }),
    field({
      label: "Контроль срока",
      name: "deadline_state",
      type: "select",
      placeholder: "Все документы",
      value: f.deadline_state,
      options: [
        { value: "overdue", label: "Просроченные" },
        { value: "warning", label: "Срок близок" },
      ],
    }),
    h(
      "div",
      { class: "filter-actions" },
      h("button", { class: "btn btn-primary", type: "submit" }, "Найти"),
      h("button", { class: "btn", type: "button", onclick: reset }, "Сбросить"),
    ),
  );

  form.document_type_id.dataset.selected = f.document_type_id || "";
  fillSelect(form.document_type_id, loadTypes());
  if (corrField) {
    form.correspondent_id.dataset.selected = f.correspondent_id || "";
    fillSelect(form.correspondent_id, loadCorrespondents());
  }
  if (execField) {
    form.executor_id.dataset.selected = f.executor_id || "";
    fillSelect(form.executor_id, loadExecutors(), (u) => u.full_name);
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const dateOrder = () => {
      const { date_from: from, date_to: to } = form;
      return from.value && to.value && from.value > to.value ? "Конец периода раньше начала" : null;
    };
    if (!validateForm(form, [["date_to", dateOrder]])) return;
    journal.filters = Object.fromEntries(Object.entries(formValues(form)).filter(([, v]) => v !== null));
    onApply();
  });

  function reset() {
    for (const el of form.elements) if (el.name) el.value = "";
    clearFieldErrors(form);
    journal.filters = {};
    onApply();
  }
  return form;
}

function numberLookup() {
  const form = h(
    "form",
    { class: "filters", novalidate: true, style: "border-radius: 4px; border-bottom: 1px solid var(--rule); margin-bottom: 14px" },
    field({ label: "Открыть карточку по регистрационному номеру", name: "number", required: true, attrs: { placeholder: "ВХ-2026-000001" } }),
    h("div", { class: "filter-actions" }, h("button", { class: "btn btn-primary", type: "submit" }, "Открыть")),
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!validateForm(form)) return;
    await withBusy(form.querySelector("[type=submit]"), async () => {
      try {
        const doc = await api.documents.byNumber(form.number.value.trim());
        navigate(`/documents/${doc.id}`);
      } catch (error) {
        handleError(error);
        if (error.status === 404) showFieldError(form, "number", "Документ с таким номером не найден");
      }
    });
  });
  return form;
}

async function exportJournal(button) {
  const { date_from, date_to, correspondent_id, status, document_type_id } = journal.filters;
  await withBusy(button, async () => {
    try {
      saveBlob(await api.exports.registrationLog({ date_from, date_to, correspondent_id, status, document_type_id }));
      toast("Файл CSV сохранён.", { type: "success", title: "Журнал выгружен" });
    } catch (error) {
      handleError(error);
    }
  });
}

async function viewDocuments(content) {
  const canSearch = can("document:search");
  const isExecutor = role() === "executor";
  const actions = [];
  if (can("document:register")) actions.push(h("a", { class: "btn btn-primary", href: "#/documents/new" }, "Зарегистрировать документ"));
  if (can("export:registry")) {
    actions.push(
      h(
        "button",
        {
          class: "btn",
          type: "button",
          title: "Учитываются период, корреспондент, статус и тип из фильтров",
          onclick: (event) => exportJournal(event.currentTarget),
        },
        "Выгрузить журнал в CSV",
      ),
    );
  }
  const subtitle = canSearch
    ? "Просроченные документы выделены красным, документы с близким сроком — жёлтым."
    : isExecutor
      ? "Документы, по которым вам назначены резолюции. Откройте карточку, чтобы прикрепить отчёт и отметить исполнение."
      : "Только просмотр. Удаление и аннулирование выполняются в карточке документа.";
  content.append(pageHead(documentsLabel(), subtitle, ...actions));

  if (!canSearch && !isExecutor) content.append(numberLookup());
  const tableBox = h("div", { class: "table-wrap" });
  const pagerBox = h("div");
  if (canSearch) {
    content.append(
      journalFilters(() => {
        journal.page = 1;
        load();
      }),
    );
  }
  content.append(tableBox, pagerBox);

  function emptyState() {
    if (canSearch && Object.keys(journal.filters).length) return emptyBox("По заданным условиям документов нет. Измените или сбросьте фильтры.");
    if (isExecutor) return emptyBox("Вам пока не назначено ни одного поручения.");
    return emptyBox(
      "Документов пока нет.",
      can("document:register") && h("a", { class: "btn btn-primary", href: "#/documents/new" }, "Зарегистрировать документ"),
    );
  }

  function load() {
    const query = { page: journal.page, page_size: journal.page_size, sort: journal.sort, ...(canSearch ? journal.filters : {}) };
    pagerBox.replaceChildren();
    return loadInto(
      tableBox,
      () => api.documents.list(query),
      (data) => {
        if (data.pages > 0 && data.page > data.pages) {
          journal.page = data.pages;
          load();
          return;
        }
        tableBox.replaceChildren(
          data.items.length
            ? documentsTable(data.items, journal.sort, (sort) => {
                journal.sort = sort;
                load();
              })
            : emptyState(),
        );
        pagerBox.replaceChildren(
          pager(
            data,
            (page) => {
              journal.page = page;
              load();
            },
            (size) => {
              journal.page_size = size;
              journal.page = 1;
              load();
            },
          ),
        );
      },
    );
  }
  await load();
}

/* ==========================================================================
   Регистрация документа
   ========================================================================== */

async function viewRegister(content, { isCurrent }) {
  content.append(pageHead("Регистрация документа", "Регистрационный номер и дата регистрации присваиваются автоматически при сохранении."));
  const body = h("div", { class: "narrow" });
  content.append(body);
  await loadInto(
    body,
    () => Promise.all([loadCorrespondents(), loadTypes()]),
    ([correspondents, types]) => {
      if (isCurrent()) body.replaceChildren(registerForm(body, correspondents, types));
    },
  );
}

const correspondentLabel = (c) => (c.inn ? `${c.name} (ИНН ${c.inn})` : c.name);

function registerForm(body, correspondents, types) {
  const today = todayISO();
  const corrField = field({
    label: "Корреспондент",
    name: "correspondent_id",
    type: "select",
    required: true,
    placeholder: "Выберите корреспондента",
    options: optionList(correspondents, correspondentLabel),
    span2: true,
  });
  if (can("correspondent:create")) {
    corrField.insertBefore(
      h(
        "div",
        { class: "hint" },
        "Нет в списке? ",
        h(
          "button",
          {
            class: "btn-link",
            type: "button",
            onclick: () =>
              openCorrespondentForm(null, (created) => {
                dropCache("correspondents");
                const select = form.correspondent_id;
                select.append(h("option", { value: created.id }, correspondentLabel(created)));
                select.value = created.id;
              }),
          },
          "Добавить корреспондента",
        ),
      ),
      corrField.querySelector(".field-error"),
    );
  }

  const submitButton = h("button", { class: "btn btn-primary", type: "submit" }, "Зарегистрировать");
  const form = h(
    "form",
    { class: "panel", novalidate: true },
    h(
      "div",
      { class: "form-grid" },
      field({ label: "Дата поступления", name: "received_date", type: "date", required: true, value: today, attrs: { max: today } }),
      field({ label: "Количество листов", name: "page_count", type: "number", required: true, value: "1", attrs: { min: 1, step: 1 } }),
      corrField,
      field({
        label: "Тип документа",
        name: "document_type_id",
        type: "select",
        required: true,
        placeholder: "Выберите тип",
        options: optionList(types.filter((t) => t.is_active)),
      }),
      field({
        label: "Срок исполнения",
        name: "execution_deadline",
        type: "date",
        required: true,
        attrs: { min: today },
        hint: "Не раньше даты регистрации",
      }),
      field({ label: "Адресат", name: "addressee", attrs: { maxlength: 255, placeholder: "Например, директору" }, span2: true }),
      field({ label: "Краткое содержание", name: "summary", type: "textarea", required: true, attrs: { minlength: 3, maxlength: 5000 }, span2: true }),
      field({
        label: "Скан документа",
        name: "file",
        type: "file",
        attrs: { accept: FILE_ACCEPT },
        span2: true,
        hint: "PDF, JPG, PNG или DOCX до 20 МБ. Прикрепляется после регистрации кнопкой «Прикрепить скан».",
      }),
    ),
    h("div", { class: "form-actions" }, submitButton, h("a", { class: "btn", href: "#/documents" }, "Отмена")),
  );

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const integerPages = () => (Number.isInteger(Number(form.page_count.value)) ? null : "Введите целое число");
    if (!validateForm(form, [["page_count", integerPages]])) return;
    const v = formValues(form);
    const payload = {
      received_date: v.received_date,
      correspondent_id: v.correspondent_id,
      addressee: v.addressee,
      summary: v.summary,
      document_type_id: v.document_type_id,
      page_count: Number(v.page_count),
      execution_deadline: v.execution_deadline,
    };
    const file = form.file.files[0] || null;
    await withBusy(submitButton, async () => {
      try {
        const doc = await api.documents.create(payload);
        body.replaceChildren(registeredPanel(doc, file));
        toast(`Присвоен номер ${doc.registration_number}.`, { type: "success", title: "Документ зарегистрирован" });
      } catch (error) {
        handleError(error, { form });
      }
    });
  });
  return form;
}

function registeredPanel(doc, initialFile) {
  let file = initialFile;
  const inputId = nextId("scan");
  const fileInput = h("input", { id: inputId, name: "file", type: "file", accept: FILE_ACCEPT });
  const state = h("div", { class: "hint" }, file ? `Выбран файл: ${file.name} (${fmtSize(file.size)})` : "Файл не выбран");
  const attachButton = h("button", { class: "btn btn-primary", type: "button", disabled: !file }, "Прикрепить скан");
  const uploadForm = h(
    "form",
    { novalidate: true, onsubmit: (event) => event.preventDefault() },
    h(
      "div",
      { class: "field" },
      h("label", { for: inputId }, "Скан документа"),
      fileInput,
      state,
      h("div", { class: "field-error", id: `${inputId}-error` }),
    ),
    h("div", { class: "form-actions", style: "margin-top: 12px" }, attachButton),
  );

  fileInput.addEventListener("change", () => {
    clearFieldErrors(uploadForm);
    file = fileInput.files[0] || null;
    state.textContent = file ? `Выбран файл: ${file.name} (${fmtSize(file.size)})` : "Файл не выбран";
    attachButton.disabled = !file;
  });
  attachButton.addEventListener("click", async () => {
    clearFieldErrors(uploadForm);
    const problem = checkFile(file);
    if (problem) {
      showFieldError(uploadForm, "file", problem);
      return;
    }
    await withBusy(attachButton, async () => {
      try {
        const attachment = await api.documents.uploadFile(doc.id, file, "source_scan");
        toast(attachment.original_filename, { type: "success", title: "Скан прикреплён" });
        state.textContent = `Прикреплён: ${attachment.original_filename} (${fmtSize(attachment.size_bytes)})`;
        file = null;
        fileInput.value = "";
      } catch (error) {
        handleError(error, { form: uploadForm });
      }
    });
    attachButton.disabled = !file;
  });

  return h(
    "div",
    { class: "panel" },
    h(
      "div",
      { class: "registered" },
      stamp(doc),
      h(
        "div",
        {},
        h("h2", {}, "Документ зарегистрирован"),
        h("p", { class: "lead", style: "margin: 6px 0 0" }, `Регистрационный номер ${doc.registration_number} от ${fmtDate(doc.registration_date)}. Срок исполнения — ${fmtDate(doc.execution_deadline)}.`),
      ),
    ),
    h("div", { style: "margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--rule-soft)" }, uploadForm),
    h(
      "div",
      { class: "form-actions" },
      h("a", { class: "btn", href: `#/documents/${doc.id}` }, "Открыть карточку"),
      h("button", { class: "btn", type: "button", onclick: () => router() }, "Зарегистрировать ещё"),
    ),
  );
}

/* ==========================================================================
   Карточка документа
   ========================================================================== */

const CARD_TABS = [
  { key: "main", title: "Основные сведения" },
  { key: "files", title: "Вложения", count: (doc) => doc.attachments.length },
  { key: "resolutions", title: "Резолюции", count: (doc) => doc.resolutions.length },
  { key: "history", title: "История", count: (doc) => doc.history.length },
  { key: "status", title: "Управление статусом" },
];

const backLink = () => h("a", { class: "back-link", href: "#/documents" }, `← ${documentsLabel()}`);

/** У исполнителя есть незакрытая резолюция по документу (для показа кнопки «Отметить исполнение»). */
function hasOwnOpenResolution(doc) {
  return (
    role() === "executor" &&
    doc.status === "на исполнении" &&
    doc.resolutions.some((r) => r.assigned_executor_id === session.me.id && r.status === "на исполнении")
  );
}

async function viewCard(content, { id, params, isCurrent }) {
  const requested = params.get("tab");
  const tab = CARD_TABS.some((t) => t.key === requested) ? requested : "main";
  content.replaceChildren(backLink(), loadingBox());
  try {
    const doc = await api.documents.get(id);
    if (isCurrent()) renderCard(content, doc, tab);
  } catch (error) {
    if (!isCurrent() || (error instanceof ApiError && error.status === 401)) return;
    handleError(error);
    const title = error.status === 403 ? "Нет доступа к документу" : error.status === 404 ? "Документ не найден" : "Карточка документа";
    content.replaceChildren(backLink(), pageHead(title), errorBox(error, () => viewCard(content, { id, params, isCurrent })));
  }
}

function renderCard(content, doc, activeTab) {
  document.title = `${doc.registration_number} — ${APP_NAME}`;
  remember([doc.correspondent, doc.document_type, ...doc.executors]);
  remember(doc.resolutions.map((r) => r.assigned_executor));
  const reload = async (tab = activeTab) => {
    try {
      const fresh = await api.documents.get(doc.id);
      if (content.isConnected) renderCard(content, fresh, tab);
    } catch (error) {
      handleError(error);
    }
  };

  const info = deadlineInfo(doc);
  const headActions = [];
  if (hasOwnOpenResolution(doc)) {
    headActions.push(h("button", { class: "btn btn-primary", type: "button", onclick: () => openExecutionDialog(doc, reload) }, "Отметить исполнение"));
  }
  if (can("document:delete")) {
    headActions.push(h("button", { class: "btn btn-danger", type: "button", onclick: (e) => deleteDocument(doc, e.currentTarget) }, "Удалить карточку"));
  }

  const head = h(
    "div",
    { class: "card-head" },
    stamp(doc),
    h(
      "div",
      {},
      h("h1", { class: "summary-title" }, doc.summary),
      h(
        "div",
        { class: "meta" },
        statusBadge(doc.status),
        h("span", {}, doc.document_type.name),
        h("span", {}, doc.correspondent.name),
        h("span", { class: `deadline-note ${info.cls}`, style: "display: inline" }, `Срок ${fmtDate(doc.execution_deadline)}${info.text ? `, ${info.text}` : ""}`),
      ),
    ),
    headActions.length ? h("div", { class: "actions" }, headActions) : h("div"),
  );

  const panel = h("div", { id: "card-panel", role: "tabpanel" });
  const tabButtons = CARD_TABS.map((t) =>
    h(
      "button",
      { type: "button", role: "tab", id: `tab-${t.key}`, "aria-controls": "card-panel", onclick: () => select(t.key) },
      t.title,
      t.count && h("span", { class: "count" }, t.count(doc)),
    ),
  );
  const renderers = { main: cardMain, files: cardFiles, resolutions: cardResolutions, history: cardHistory, status: cardStatus };

  function select(key) {
    activeTab = key;
    for (const button of tabButtons) button.setAttribute("aria-selected", String(button.id === `tab-${key}`));
    panel.setAttribute("aria-labelledby", `tab-${key}`);
    history.replaceState(null, "", `#/documents/${doc.id}${key === "main" ? "" : `?tab=${key}`}`);
    panel.replaceChildren();
    renderers[key](panel, doc, reload);
  }

  content.replaceChildren(backLink(), head, h("div", { class: "tabs", role: "tablist", "aria-label": "Разделы карточки" }, tabButtons), panel);
  select(activeTab);
}

/* ---------- Основные сведения ---------- */

function cardMain(panel, doc, reload) {
  const info = deadlineInfo(doc);
  const rows = [
    ["Регистрационный номер", doc.registration_number],
    ["Дата регистрации", fmtDate(doc.registration_date)],
    ["Дата поступления", fmtDate(doc.received_date)],
    ["Корреспондент", correspondentLabel(doc.correspondent)],
    ["Адресат", doc.addressee || "—"],
    ["Тип документа", doc.document_type.name],
    ["Количество листов", String(doc.page_count)],
    ["Краткое содержание", doc.summary],
    ["Срок исполнения", `${fmtDate(doc.execution_deadline)}${info.text ? ` (${info.text})` : ""}`],
    ["Статус", statusBadge(doc.status)],
    ["Исполнители", doc.executors.map((e) => e.full_name).join(", ") || "не назначены"],
    ["Карточка создана", fmtDateTime(doc.created_at)],
    ["Последнее изменение", fmtDateTime(doc.updated_at)],
  ];
  if (doc.archived_at) rows.push(["Передана в архив", fmtDateTime(doc.archived_at)]);

  const box = h("div", { class: "panel" });
  if (can("document:edit") && doc.status === ARCHIVED) box.append(h("div", { class: "note" }, "Карточка в архиве, реквизиты не редактируются."));
  box.append(h("dl", { class: "props" }, rows.flatMap(([label, value]) => [h("dt", {}, label), h("dd", {}, value)])));
  if (can("document:edit") && doc.status !== ARCHIVED) {
    box.append(
      h("div", { class: "form-actions" }, h("button", { class: "btn", type: "button", onclick: () => editDocument(panel, doc, reload) }, "Редактировать реквизиты")),
    );
  }
  panel.append(box);
}

async function editDocument(panel, doc, reload) {
  panel.replaceChildren(loadingBox());
  let correspondents;
  let types;
  try {
    [correspondents, types] = await Promise.all([loadCorrespondents(), loadTypes()]);
  } catch (error) {
    handleError(error);
    panel.replaceChildren(errorBox(error, () => editDocument(panel, doc, reload)));
    return;
  }
  const save = h("button", { class: "btn btn-primary", type: "submit" }, "Сохранить изменения");
  const form = h(
    "form",
    { class: "panel narrow", novalidate: true },
    h("h2", { style: "margin-bottom: 14px" }, "Редактирование реквизитов"),
    h(
      "div",
      { class: "form-grid" },
      field({ label: "Дата поступления", name: "received_date", type: "date", required: true, value: doc.received_date, attrs: { max: doc.registration_date } }),
      field({ label: "Количество листов", name: "page_count", type: "number", required: true, value: String(doc.page_count), attrs: { min: 1, step: 1 } }),
      field({
        label: "Корреспондент",
        name: "correspondent_id",
        type: "select",
        required: true,
        options: optionList(correspondents, correspondentLabel),
        value: doc.correspondent.id,
        span2: true,
      }),
      field({
        label: "Тип документа",
        name: "document_type_id",
        type: "select",
        required: true,
        options: optionList(types.filter((t) => t.is_active || t.id === doc.document_type.id)),
        value: doc.document_type.id,
      }),
      field({
        label: "Срок исполнения",
        name: "execution_deadline",
        type: "date",
        required: true,
        value: doc.execution_deadline,
        attrs: { min: doc.registration_date },
        hint: `Не раньше даты регистрации (${fmtDate(doc.registration_date)})`,
      }),
      field({ label: "Адресат", name: "addressee", value: doc.addressee, attrs: { maxlength: 255 }, span2: true }),
      field({ label: "Краткое содержание", name: "summary", type: "textarea", required: true, value: doc.summary, attrs: { minlength: 3, maxlength: 5000 }, span2: true }),
    ),
    h(
      "div",
      { class: "form-actions" },
      save,
      h(
        "button",
        {
          class: "btn",
          type: "button",
          onclick: () => {
            panel.replaceChildren();
            cardMain(panel, doc, reload);
          },
        },
        "Отмена",
      ),
    ),
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const integerPages = () => (Number.isInteger(Number(form.page_count.value)) ? null : "Введите целое число");
    if (!validateForm(form, [["page_count", integerPages]])) return;
    const v = formValues(form);
    await withBusy(save, async () => {
      try {
        await api.documents.update(doc.id, {
          received_date: v.received_date,
          correspondent_id: v.correspondent_id,
          addressee: v.addressee,
          summary: v.summary,
          document_type_id: v.document_type_id,
          page_count: Number(v.page_count),
          execution_deadline: v.execution_deadline,
        });
        toast("Реквизиты карточки обновлены.", { type: "success", title: "Изменения сохранены" });
        reload("main");
      } catch (error) {
        handleError(error, { form });
      }
    });
  });
  panel.replaceChildren(form);
}

/* ---------- Вложения ---------- */

async function downloadAttachment(attachment, button) {
  await withBusy(button, async () => {
    try {
      saveBlob(await api.files.download(attachment.id));
    } catch (error) {
      handleError(error);
    }
  });
}

function cardFiles(panel, doc, reload) {
  if (can("file:attach") && doc.status !== ARCHIVED) panel.append(uploadBlock(doc, reload));
  const wrap = h("div", { class: "table-wrap" });
  if (!doc.attachments.length) {
    wrap.append(emptyBox("Файлов пока нет."));
  } else {
    wrap.append(
      h(
        "table",
        {},
        h("caption", { class: "sr-only" }, "Вложения"),
        h("thead", {}, h("tr", {}, ["Файл", "Вид", "Размер", "Загрузил", "Дата загрузки", ""].map((t) => h("th", { scope: "col" }, t)))),
        h(
          "tbody",
          {},
          doc.attachments.map((a) =>
            h(
              "tr",
              {},
              h("td", {}, a.original_filename),
              h("td", {}, ATTACHMENT_TYPES[a.attachment_type] || a.attachment_type),
              h("td", { class: "nowrap" }, fmtSize(a.size_bytes)),
              h("td", {}, a.uploader.full_name),
              h("td", { class: "nowrap" }, fmtDateTime(a.created_at)),
              h(
                "td",
                { class: "actions-cell" },
                h("button", { class: "btn btn-sm", type: "button", onclick: (e) => downloadAttachment(a, e.currentTarget) }, "Скачать"),
              ),
            ),
          ),
        ),
      ),
    );
  }
  panel.append(wrap);
}

function uploadBlock(doc, reload) {
  const isExecutor = role() === "executor";
  const kinds = isExecutor ? ["execution_report", "other"] : ["source_scan", "execution_report", "other"];
  const submit = h("button", { class: "btn btn-primary", type: "submit" }, "Прикрепить файл");
  const form = h(
    "form",
    { class: "panel", novalidate: true, style: "margin-bottom: 16px" },
    h("h2", { style: "margin-bottom: 12px" }, isExecutor ? "Отчётные материалы" : "Прикрепить файл"),
    h(
      "div",
      { class: "form-grid" },
      field({ label: "Файл", name: "file", type: "file", required: true, attrs: { accept: FILE_ACCEPT }, hint: "PDF, JPG, PNG или DOCX до 20 МБ" }),
      field({
        label: "Вид вложения",
        name: "attachment_type",
        type: "select",
        required: true,
        options: kinds.map((k) => ({ value: k, label: ATTACHMENT_TYPES[k] })),
        value: kinds[0],
      }),
    ),
    h("div", { class: "form-actions", style: "margin-top: 14px" }, submit),
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!validateForm(form)) return;
    const file = form.file.files[0];
    await withBusy(submit, async () => {
      try {
        const attachment = await api.documents.uploadFile(doc.id, file, form.attachment_type.value);
        toast(attachment.original_filename, { type: "success", title: "Файл прикреплён" });
        reload("files");
      } catch (error) {
        handleError(error, { form });
      }
    });
  });
  return form;
}

/* ---------- Резолюции ---------- */

function cardResolutions(panel, doc, reload) {
  if (can("resolution:create")) {
    panel.append(
      h(
        "div",
        { class: "actions", style: "margin-bottom: 16px" },
        h("button", { class: "btn btn-primary", type: "button", onclick: () => openResolutionForm(doc, null, () => reload("resolutions")) }, "Добавить резолюцию"),
      ),
    );
  }
  const list = h("div", { class: "panel" });
  panel.append(list);
  const render = (resolutions) =>
    list.replaceChildren(
      ...(resolutions.length
        ? resolutions.map((r) => resolutionItem(doc, r, reload))
        : [emptyBox(can("resolution:create") ? "Резолюций пока нет. Добавьте резолюцию, чтобы назначить исполнителя и срок." : "Резолюций пока нет.")]),
    );
  // Резолюции загружаются отдельным запросом (GET /incoming/{id}/resolutions), если роли это разрешено
  if (can("resolution:view")) loadInto(list, () => api.documents.resolutions(doc.id), render);
  else render(doc.resolutions);
}

function resolutionItem(doc, r, reload) {
  const done = r.status !== "на исполнении";
  return h(
    "article",
    { class: `resolution${done ? " done" : ""}` },
    h("p", { class: "res-text" }, r.text),
    h(
      "div",
      { class: "res-meta" },
      h("span", {}, "Исполнитель: ", h("b", {}, r.assigned_executor.full_name)),
      h("span", {}, "Срок: ", h("b", {}, fmtDate(r.deadline))),
      h("span", {}, "Автор: ", r.author.full_name),
      h("span", {}, "Создана: ", fmtDateTime(r.created_at)),
      h("span", {}, h("span", { class: `status ${done ? "status-res-done" : "status-res-open"}` }, r.status)),
      done && r.executed_at && h("span", {}, "Исполнена: ", fmtDateTime(r.executed_at)),
    ),
    can("resolution:edit") &&
      !done &&
      h(
        "div",
        { class: "res-actions" },
        h("button", { class: "btn btn-sm", type: "button", onclick: () => openResolutionForm(doc, r, () => reload("resolutions")) }, "Изменить резолюцию"),
      ),
  );
}

async function openResolutionForm(doc, existing, onSaved) {
  let executors;
  try {
    executors = await loadExecutors();
  } catch (error) {
    handleError(error);
    return;
  }
  const options = optionList(executors, (u) => `${u.full_name} (${u.department.name})`);
  if (existing && !executors.some((u) => u.id === existing.assigned_executor_id)) {
    options.unshift({ value: existing.assigned_executor_id, label: `${existing.assigned_executor.full_name} (неактивен)` });
  }
  const submit = h("button", { class: "btn btn-primary", type: "submit" }, existing ? "Сохранить резолюцию" : "Добавить резолюцию");
  const form = h(
    "form",
    { novalidate: true },
    h(
      "div",
      { class: "form-grid" },
      field({ label: "Текст поручения", name: "text", type: "textarea", required: true, value: existing?.text, attrs: { minlength: 3, maxlength: 5000 }, span2: true }),
      field({
        label: "Исполнитель",
        name: "assigned_executor_id",
        type: "select",
        required: true,
        placeholder: "Выберите исполнителя",
        options,
        value: existing?.assigned_executor_id,
      }),
      field({
        label: "Срок исполнения",
        name: "deadline",
        type: "date",
        required: true,
        value: existing?.deadline ?? doc.execution_deadline,
        attrs: { min: doc.registration_date },
        hint: `Не раньше даты регистрации (${fmtDate(doc.registration_date)})`,
      }),
    ),
    h("div", { class: "form-actions" }, submit, h("button", { class: "btn", type: "button", onclick: () => close() }, "Отмена")),
  );
  const close = openModal({ title: existing ? "Изменение резолюции" : `Резолюция по документу ${doc.registration_number}`, body: form });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!validateForm(form)) return;
    const v = formValues(form);
    const payload = { text: v.text, assigned_executor_id: v.assigned_executor_id, deadline: v.deadline };
    await withBusy(submit, async () => {
      try {
        if (existing) {
          await api.resolutions.update(existing.id, payload);
          toast("Изменения резолюции сохранены.", { type: "success", title: "Резолюция сохранена" });
        } else {
          const created = await api.documents.createResolution(doc.id, payload);
          toast(`Исполнитель: ${created.assigned_executor.full_name}.`, { type: "success", title: "Резолюция добавлена" });
        }
        close();
        onSaved();
      } catch (error) {
        handleError(error, { form });
      }
    });
  });
}

/* ---------- История ---------- */

function historyValue(key, value) {
  if (value === null || value === undefined || value === "") return "—";
  if (key.endsWith("_id")) return names.get(String(value)) || "другое значение";
  if (/^\d{4}-\d{2}-\d{2}$/.test(String(value))) return fmtDate(value);
  return String(value);
}

function historyDetails(entry) {
  const meta = entry.metadata || {};
  const parts = [];
  if (entry.comment) parts.push(h("div", {}, entry.comment));
  if (meta.registration_number) parts.push(h("div", { class: "muted" }, `Присвоен номер ${meta.registration_number}`));
  if (meta.filename) {
    parts.push(h("div", { class: "muted" }, `${meta.filename} (${ATTACHMENT_TYPES[meta.type] || meta.type}, ${fmtSize(meta.size_bytes || 0)})`));
  }
  if (meta.executor_id) parts.push(h("div", { class: "muted" }, `Исполнитель: ${historyValue("executor_id", meta.executor_id)}; срок ${fmtDate(meta.deadline)}`));
  if (meta.changes) {
    parts.push(
      h(
        "ul",
        { class: "change-list" },
        Object.entries(meta.changes).map(([key, change]) =>
          h("li", {}, `${FIELD_LABELS[key] || key}: ${historyValue(key, change.old)} → ${historyValue(key, change.new)}`),
        ),
      ),
    );
  }
  return parts.length ? parts : "—";
}

function cardHistory(panel, doc) {
  const wrap = h("div", { class: "table-wrap" });
  panel.append(wrap);
  // Имена для расшифровки идентификаторов в изменениях (только из доступных роли справочников)
  const lookups = [loadTypes()];
  if (can("correspondent:view")) lookups.push(loadCorrespondents());
  if (canListExecutors()) lookups.push(loadExecutors());
  loadInto(
    wrap,
    async () => {
      await Promise.allSettled(lookups);
      return api.documents.history(doc.id);
    },
    (entries) => {
      if (!entries.length) {
        wrap.replaceChildren(emptyBox("Записей нет."));
        return;
      }
      wrap.replaceChildren(
        h(
          "table",
          {},
          h("caption", { class: "sr-only" }, "История действий по документу"),
          h("thead", {}, h("tr", {}, ["Дата и время", "Пользователь", "Действие", "Статус", "Подробности"].map((t) => h("th", { scope: "col" }, t)))),
          h(
            "tbody",
            {},
            entries.map((entry) =>
              h(
                "tr",
                {},
                h("td", { class: "nowrap" }, fmtDateTime(entry.created_at)),
                h("td", {}, entry.user.full_name),
                h("td", {}, HISTORY_ACTIONS[entry.action] || entry.action),
                h(
                  "td",
                  { class: "nowrap" },
                  entry.new_status
                    ? [entry.old_status ? [statusBadge(entry.old_status), " → "] : null, statusBadge(entry.new_status)]
                    : "—",
                ),
                h("td", {}, historyDetails(entry)),
              ),
            ),
          ),
        ),
      );
    },
  );
}

/* ---------- Управление статусом ---------- */

function cardStatus(panel, doc, reload) {
  const index = STATUSES.indexOf(doc.status);
  panel.append(
    h(
      "ol",
      { class: "lifecycle", "aria-label": "Жизненный цикл документа" },
      STATUSES.map((s, i) => h("li", { class: i === index ? "current" : i < index ? "passed" : null, "aria-current": i === index ? "step" : null }, s)),
    ),
  );
  const box = h("div", { class: "panel status-actions" });
  panel.append(box);

  let buttons = (STATUS_BUTTONS[role()] || []).filter((b) => b.from === doc.status);
  if (role() === "executor" && !hasOwnOpenResolution(doc)) buttons = [];

  if (can("document:change_status") && buttons.length) {
    const form = h(
      "form",
      { novalidate: true, onsubmit: (event) => event.preventDefault() },
      field({ label: "Комментарий", name: "comment", type: "textarea", attrs: { maxlength: 2000, placeholder: "Необязательно. Сохраняется в истории." } }),
    );
    box.append(
      h("h2", {}, "Смена статуса"),
      h("div", {}, "Текущий статус: ", statusBadge(doc.status)),
      form,
      h(
        "div",
        { class: "actions" },
        buttons.map((b) =>
          h("button", { class: "btn btn-primary", type: "button", onclick: (e) => changeStatus(doc, b, form.comment.value, reload, e.currentTarget) }, b.label),
        ),
      ),
    );
  }

  if (can("document:annul") && doc.status !== "зарегистрирован") {
    const form = h(
      "form",
      { novalidate: true, onsubmit: (event) => event.preventDefault() },
      field({ label: "Причина аннулирования", name: "comment", type: "textarea", attrs: { maxlength: 2000, placeholder: "Например, ошибочная регистрация" } }),
    );
    box.append(
      h("h2", {}, "Аннулирование"),
      h("p", { style: "margin: 0" }, "Возвращает документ в статус «зарегистрирован». Действие записывается в историю."),
      form,
      h("div", { class: "actions" }, h("button", { class: "btn btn-danger", type: "button", onclick: (e) => annulDocument(doc, form.comment.value, reload, e.currentTarget) }, "Аннулировать")),
    );
  }

  if (!box.childElementCount) {
    const hint =
      role() === "manager"
        ? "Руководитель не меняет статус вручную: документ переходит «на исполнении» автоматически при создании резолюции."
        : role() === "executor"
          ? "Отметить исполнение можно, пока ваша резолюция по документу не исполнена и документ находится на исполнении."
          : "Для текущего статуса документа действий нет.";
    box.append(h("p", { style: "margin: 0" }, hint));
  }
}

async function changeStatus(doc, transition, comment, reload, button) {
  if (transition.confirm) {
    const ok = await confirmDialog({
      title: transition.label,
      message: `Документ ${doc.registration_number} будет передан в архив. После этого реквизиты карточки нельзя изменить.`,
      confirmText: transition.label,
      danger: false,
    });
    if (!ok) return;
  }
  await withBusy(button, async () => {
    try {
      const updated = await api.documents.changeStatus(doc.id, transition.to, comment.trim());
      toast(`Новый статус: ${updated.status}.`, { type: "success", title: "Статус изменён" });
      reload("status");
    } catch (error) {
      handleError(error);
    }
  });
}

function openExecutionDialog(doc, reload) {
  const submit = h("button", { class: "btn btn-primary", type: "submit" }, "Отметить исполнение");
  const form = h(
    "form",
    { novalidate: true },
    h("p", { style: "margin-top: 0" }, "Перед отметкой прикрепите отчётные материалы во вкладке «Вложения», если они есть."),
    field({ label: "Комментарий", name: "comment", type: "textarea", attrs: { maxlength: 2000, placeholder: "Например, ответ направлен письмом № 15" } }),
    h("div", { class: "form-actions" }, submit, h("button", { class: "btn", type: "button", onclick: () => close() }, "Отмена")),
  );
  const close = openModal({ title: `Исполнение по документу ${doc.registration_number}`, body: form });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await withBusy(submit, async () => {
      try {
        const updated = await api.documents.changeStatus(doc.id, "исполнен", form.comment.value.trim());
        close();
        if (updated.status === "исполнен") toast("Документ переведён в статус «исполнен».", { type: "success", title: "Исполнение отмечено" });
        else toast("Ваша резолюция исполнена. Документ останется на исполнении, пока не отчитаются остальные исполнители.", { type: "success", title: "Исполнение отмечено" });
        reload("status");
      } catch (error) {
        handleError(error, { form });
      }
    });
  });
}

async function annulDocument(doc, comment, reload, button) {
  const ok = await confirmDialog({
    title: "Аннулирование документа",
    message: `Документ ${doc.registration_number} вернётся в статус «зарегистрирован».`,
    confirmText: "Аннулировать",
  });
  if (!ok) return;
  await withBusy(button, async () => {
    try {
      await api.documents.changeStatus(doc.id, "зарегистрирован", comment.trim());
      toast(`Документ ${doc.registration_number} возвращён в статус «зарегистрирован».`, { type: "success", title: "Документ аннулирован" });
      reload("status");
    } catch (error) {
      handleError(error);
    }
  });
}

async function deleteDocument(doc, button) {
  const ok = await confirmDialog({
    title: "Удаление карточки",
    message: `Карточка ${doc.registration_number} будет удалена вместе с резолюциями, вложениями и историей. Действие необратимо. Удаляйте только ошибочные записи и дубликаты.`,
    confirmText: "Удалить карточку",
  });
  if (!ok) return;
  await withBusy(button, async () => {
    try {
      await api.documents.remove(doc.id);
      toast(`Карточка ${doc.registration_number} удалена.`, { type: "success", title: "Карточка удалена" });
      navigate("/documents");
    } catch (error) {
      handleError(error);
    }
  });
}

/* ==========================================================================
   Корреспонденты
   ========================================================================== */

const correspondentsState = { page: 1, page_size: 20, search: "", inn: "" };

function openCorrespondentForm(existing, onSaved) {
  const submit = h("button", { class: "btn btn-primary", type: "submit" }, existing ? "Сохранить" : "Добавить корреспондента");
  const form = h(
    "form",
    { novalidate: true },
    h(
      "div",
      { class: "form-grid" },
      field({ label: "Наименование", name: "name", required: true, value: existing?.name, attrs: { minlength: 2, maxlength: 500 }, span2: true }),
      field({
        label: "ИНН",
        name: "inn",
        value: existing?.inn,
        attrs: { pattern: "\\d{10}|\\d{12}", title: "10 цифр для организации или 12 для физического лица", inputmode: "numeric" },
        hint: "10 или 12 цифр; для граждан можно не заполнять",
      }),
      field({ label: "Телефон", name: "phone", value: existing?.phone, attrs: { maxlength: 64, placeholder: "+7 495 000-00-00" } }),
      field({ label: "Email", name: "email", type: "email", value: existing?.email, attrs: { maxlength: 255 } }),
      field({ label: "ФИО подписанта", name: "signer_full_name", value: existing?.signer_full_name, attrs: { maxlength: 255 } }),
      field({ label: "Адрес", name: "address", type: "textarea", value: existing?.address, attrs: { maxlength: 2000 }, span2: true }),
    ),
    h("div", { class: "form-actions" }, submit, h("button", { class: "btn", type: "button", onclick: () => close() }, "Отмена")),
  );
  const close = openModal({ title: existing ? "Изменение корреспондента" : "Новый корреспондент", body: form });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!validateForm(form)) return;
    const values = formValues(form);
    await withBusy(submit, async () => {
      try {
        const saved = existing ? await api.correspondents.update(existing.id, values) : await api.correspondents.create(values);
        dropCache("correspondents");
        toast(saved.name, { type: "success", title: existing ? "Корреспондент сохранён" : "Корреспондент добавлен" });
        close();
        onSaved(saved);
      } catch (error) {
        handleError(error, { form });
      }
    });
  });
}

async function editCorrespondent(id, button, onSaved) {
  await withBusy(button, async () => {
    try {
      openCorrespondentForm(await api.correspondents.get(id), onSaved);
    } catch (error) {
      handleError(error);
    }
  });
}

async function viewCorrespondents(content) {
  const st = correspondentsState;
  const tableBox = h("div", { class: "table-wrap" });
  const pagerBox = h("div");
  const add = can("correspondent:create")
    ? h("button", { class: "btn btn-primary", type: "button", onclick: () => openCorrespondentForm(null, () => load()) }, "Добавить корреспондента")
    : null;
  content.append(pageHead("Корреспонденты", "Организации и граждане, от которых поступают документы.", add));

  const filters = h(
    "form",
    { class: "filters", role: "search", novalidate: true },
    field({ label: "Поиск", name: "search", type: "search", value: st.search, attrs: { placeholder: "Наименование или ФИО подписанта" } }),
    field({ label: "ИНН", name: "inn", value: st.inn, attrs: { inputmode: "numeric", maxlength: 12 } }),
    h(
      "div",
      { class: "filter-actions" },
      h("button", { class: "btn btn-primary", type: "submit" }, "Найти"),
      h(
        "button",
        {
          class: "btn",
          type: "button",
          onclick: () => {
            filters.search.value = "";
            filters.inn.value = "";
            st.search = "";
            st.inn = "";
            st.page = 1;
            load();
          },
        },
        "Сбросить",
      ),
    ),
  );
  filters.addEventListener("submit", (event) => {
    event.preventDefault();
    st.search = filters.search.value.trim();
    st.inn = filters.inn.value.trim();
    st.page = 1;
    load();
  });
  content.append(filters, tableBox, pagerBox);

  function load() {
    pagerBox.replaceChildren();
    return loadInto(
      tableBox,
      () => api.correspondents.list({ page: st.page, page_size: st.page_size, search: st.search, inn: st.inn }),
      (data) => {
        if (!data.items.length) {
          tableBox.replaceChildren(
            emptyBox(st.search || st.inn ? "По заданным условиям корреспондентов нет." : "Корреспондентов пока нет.", add && !st.search && !st.inn ? add.cloneNode(true) : null),
          );
          tableBox.querySelector(".state-box .btn")?.addEventListener("click", () => openCorrespondentForm(null, () => load()));
        } else {
          tableBox.replaceChildren(
            h(
              "table",
              { class: "registry-table" },
              h("caption", { class: "sr-only" }, "Корреспонденты"),
              h("thead", {}, h("tr", {}, ["Наименование", "ИНН", "Адрес", "Телефон", "Email", "Подписант", ""].map((t) => h("th", { scope: "col" }, t)))),
              h(
                "tbody",
                {},
                data.items.map((c) =>
                  h(
                    "tr",
                    {},
                    h("td", {}, h("b", {}, c.name)),
                    h("td", { class: "nowrap" }, c.inn || "—"),
                    h("td", {}, c.address || "—"),
                    h("td", { class: "nowrap" }, c.phone || "—"),
                    h("td", {}, c.email || "—"),
                    h("td", {}, c.signer_full_name || "—"),
                    h(
                      "td",
                      { class: "actions-cell" },
                      can("correspondent:edit") &&
                        h("button", { class: "btn btn-sm", type: "button", onclick: (e) => editCorrespondent(c.id, e.currentTarget, () => load()) }, "Изменить"),
                    ),
                  ),
                ),
              ),
            ),
          );
        }
        pagerBox.replaceChildren(
          pager(
            data,
            (page) => {
              st.page = page;
              load();
            },
            (size) => {
              st.page_size = size;
              st.page = 1;
              load();
            },
          ),
        );
      },
    );
  }
  await load();
}

/* ==========================================================================
   Отчёты и выгрузка журнала
   ========================================================================== */

function periodCheck(form, fromName, toName) {
  return () => {
    const from = form[fromName].value;
    const to = form[toName].value;
    return from && to && from > to ? "Конец периода раньше начала" : null;
  };
}

/** Необязательные фильтры отчёта/выгрузки: только те, для которых роли доступен справочник. */
function reportFilterFields(form, { withExecutor }) {
  const fields = [
    field({ label: "Статус", name: "status", type: "select", placeholder: "Любой", options: statusOptions() }),
    field({ label: "Тип документа", name: "document_type_id", type: "select", placeholder: "Любой" }),
  ];
  if (can("correspondent:view")) fields.push(field({ label: "Корреспондент", name: "correspondent_id", type: "select", placeholder: "Любой" }));
  if (withExecutor && canListExecutors()) fields.push(field({ label: "Исполнитель", name: "executor_id", type: "select", placeholder: "Любой" }));
  queueMicrotask(() => {
    fillSelect(form.document_type_id, loadTypes());
    if (form.correspondent_id) fillSelect(form.correspondent_id, loadCorrespondents());
    if (form.executor_id) fillSelect(form.executor_id, loadExecutors(), (u) => u.full_name);
  });
  return fields;
}

function reportPanel() {
  const now = new Date();
  const monthStart = isoDate(new Date(now.getFullYear(), now.getMonth(), 1));
  const submit = h("button", { class: "btn btn-primary", type: "submit" }, "Сформировать PDF");
  const form = h("form", { class: "panel", novalidate: true });
  append(
    form,
    h("h2", {}, "PDF-отчёт"),
    h("p", { class: "lead" }, "Формируется на сервере по данным системы. Период отбирается по дате регистрации."),
    h(
      "fieldset",
      { style: "border: 0; padding: 0; margin: 0 0 16px" },
      h("legend", { style: "font-weight: 600; font-size: 13px; margin-bottom: 8px" }, "Вид отчёта"),
      REPORT_TYPES.map((t, i) =>
        h(
          "label",
          { style: "display: flex; gap: 10px; align-items: flex-start; padding: 6px 0; cursor: pointer" },
          h("input", { type: "radio", name: "report_type", value: t.value, checked: i === 0, style: "margin-top: 4px" }),
          h("span", {}, h("b", {}, t.title), h("span", { class: "muted", style: "display: block" }, t.text)),
        ),
      ),
    ),
    h(
      "div",
      { class: "form-grid" },
      field({ label: "Период с", name: "period_from", type: "date", required: true, value: monthStart }),
      field({ label: "по", name: "period_to", type: "date", required: true, value: todayISO() }),
      ...reportFilterFields(form, { withExecutor: true }),
    ),
    h("div", { class: "form-actions" }, submit),
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!validateForm(form, [["period_to", periodCheck(form, "period_from", "period_to")]])) return;
    const values = formValues(form);
    await withBusy(submit, async () => {
      try {
        saveBlob(await api.reports.generate(values));
        const title = REPORT_TYPES.find((t) => t.value === values.report_type)?.title;
        toast(`${title}, ${fmtDate(values.period_from)} — ${fmtDate(values.period_to)}.`, { type: "success", title: "Отчёт сформирован" });
      } catch (error) {
        handleError(error, { form });
      }
    });
  });
  return form;
}

function exportPanel() {
  const submit = h("button", { class: "btn btn-primary", type: "submit" }, "Выгрузить CSV");
  const form = h("form", { class: "panel", novalidate: true });
  append(
    form,
    h("h2", {}, "Журнал регистрации (CSV)"),
    h("p", { class: "lead" }, "Файл открывается в Excel: кодировка UTF-8, разделитель — точка с запятой. Без периода выгружается весь журнал."),
    h(
      "div",
      { class: "form-grid" },
      field({ label: "Зарегистрированы с", name: "date_from", type: "date" }),
      field({ label: "по", name: "date_to", type: "date" }),
      ...reportFilterFields(form, { withExecutor: false }),
    ),
    h("div", { class: "form-actions" }, submit),
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!validateForm(form, [["date_to", periodCheck(form, "date_from", "date_to")]])) return;
    await withBusy(submit, async () => {
      try {
        saveBlob(await api.exports.registrationLog(formValues(form)));
        toast("Файл CSV сохранён.", { type: "success", title: "Журнал выгружен" });
      } catch (error) {
        handleError(error, { form });
      }
    });
  });
  return form;
}

async function viewReports(content) {
  const title = can("report:generate") && can("export:registry") ? "Отчёты и выгрузка" : can("report:generate") ? "Отчёты" : "Выгрузка журнала";
  content.append(pageHead(title));
  const body = h("div", { class: "narrow" });
  if (can("report:generate")) body.append(reportPanel());
  if (can("export:registry")) body.append(exportPanel());
  content.append(body);
}

/* ==========================================================================
   Пользователи (администратор)
   ========================================================================== */

const usersState = { page: 1, page_size: 20, search: "", role: "", is_active: "" };
const roleOptions = () => Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }));

async function openUserForm(existing, onSaved) {
  let departments;
  let positions;
  try {
    [departments, positions] = await Promise.all([loadDepartments(), loadPositions()]);
  } catch (error) {
    handleError(error);
    return;
  }
  const submit = h("button", { class: "btn btn-primary", type: "submit" }, existing ? "Сохранить" : "Зарегистрировать пользователя");
  const grid = h(
    "div",
    { class: "form-grid" },
    field({ label: "ФИО", name: "full_name", required: true, value: existing?.full_name, attrs: { minlength: 2, maxlength: 255 }, span2: true }),
    !existing &&
      field({
        label: "Логин",
        name: "login",
        required: true,
        attrs: { pattern: "[A-Za-z0-9_.\\-]{3,64}", title: "От 3 до 64 символов: латиница, цифры, точка, дефис, подчёркивание", autocomplete: "off" },
      }),
    field({ label: "Email", name: "email", type: "email", required: true, value: existing?.email, attrs: { maxlength: 255 } }),
    !existing &&
      field({
        label: "Пароль",
        name: "password",
        type: "password",
        required: true,
        attrs: { minlength: 8, maxlength: 128, autocomplete: "new-password" },
        hint: "Не короче 8 символов",
      }),
    field({ label: "Роль", name: "role", type: "select", required: true, placeholder: "Выберите роль", options: roleOptions(), value: existing?.role }),
    field({
      label: "Подразделение",
      name: "department_id",
      type: "select",
      required: true,
      placeholder: "Выберите подразделение",
      options: optionList(departments),
      value: existing?.department?.id,
    }),
    field({ label: "Должность", name: "position_id", type: "select", placeholder: "Не указана", options: optionList(positions), value: existing?.position?.id }),
  );
  const form = h(
    "form",
    { novalidate: true },
    existing && h("p", { class: "muted", style: "margin-top: 0" }, `Логин: ${existing.login}`),
    grid,
    h("div", { class: "form-actions" }, submit, h("button", { class: "btn", type: "button", onclick: () => close() }, "Отмена")),
  );
  const close = openModal({ title: existing ? "Изменение пользователя" : "Новый пользователь", body: form });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!validateForm(form)) return;
    const values = formValues(form);
    await withBusy(submit, async () => {
      try {
        const saved = existing ? await api.users.update(existing.id, values) : await api.users.create(values);
        dropCache("executors");
        if (existing && existing.id === session.me.id) {
          session.me = { ...session.me, full_name: saved.full_name };
          $("#user-name").textContent = saved.full_name;
        }
        toast(saved.full_name, { type: "success", title: existing ? "Пользователь сохранён" : "Пользователь зарегистрирован" });
        close();
        onSaved();
      } catch (error) {
        handleError(error, { form });
      }
    });
  });
}

async function editUser(id, button, onSaved) {
  await withBusy(button, async () => {
    try {
      const user = await api.users.get(id);
      await openUserForm(user, onSaved);
    } catch (error) {
      handleError(error);
    }
  });
}

async function deactivateUser(user, button, onDone) {
  const ok = await confirmDialog({
    title: "Деактивация пользователя",
    message: `${user.full_name} (${user.login}) больше не сможет войти в систему. Учётная запись и история действий сохранятся.`,
    confirmText: "Деактивировать",
  });
  if (!ok) return;
  await withBusy(button, async () => {
    try {
      await api.users.deactivate(user.id);
      dropCache("executors");
      toast(user.full_name, { type: "success", title: "Пользователь деактивирован" });
      onDone();
    } catch (error) {
      handleError(error);
    }
  });
}

async function viewUsers(content) {
  const st = usersState;
  const tableBox = h("div", { class: "table-wrap" });
  const pagerBox = h("div");
  const add = can("user:create") ? h("button", { class: "btn btn-primary", type: "button", onclick: () => openUserForm(null, () => load()) }, "Добавить пользователя") : null;
  content.append(pageHead("Пользователи", "Учётные записи сотрудников. Пользователи не удаляются: вместо удаления выполняется деактивация.", add));

  const filters = h(
    "form",
    { class: "filters", role: "search", novalidate: true },
    field({ label: "Поиск", name: "search", type: "search", value: st.search, attrs: { placeholder: "ФИО, логин или email" } }),
    field({ label: "Роль", name: "role", type: "select", placeholder: "Все роли", options: roleOptions(), value: st.role }),
    field({
      label: "Состояние",
      name: "is_active",
      type: "select",
      placeholder: "Все",
      value: st.is_active,
      options: [
        { value: "true", label: "Активные" },
        { value: "false", label: "Деактивированные" },
      ],
    }),
    h("div", { class: "filter-actions" }, h("button", { class: "btn btn-primary", type: "submit" }, "Найти")),
  );
  filters.addEventListener("submit", (event) => {
    event.preventDefault();
    st.search = filters.search.value.trim();
    st.role = filters.role.value;
    st.is_active = filters.is_active.value;
    st.page = 1;
    load();
  });
  content.append(filters, tableBox, pagerBox);

  function load() {
    pagerBox.replaceChildren();
    return loadInto(
      tableBox,
      () => api.users.list({ page: st.page, page_size: st.page_size, search: st.search, role: st.role, is_active: st.is_active }),
      (data) => {
        tableBox.replaceChildren(
          data.items.length
            ? h(
                "table",
                { class: "registry-table" },
                h("caption", { class: "sr-only" }, "Пользователи"),
                h(
                  "thead",
                  {},
                  h("tr", {}, ["ФИО и логин", "Email", "Роль", "Подразделение", "Должность", "Состояние", ""].map((t) => h("th", { scope: "col" }, t))),
                ),
                h(
                  "tbody",
                  {},
                  data.items.map((u) =>
                    h(
                      "tr",
                      {},
                      h("td", {}, h("b", {}, u.full_name), h("div", { class: "muted" }, u.login)),
                      h("td", {}, u.email),
                      h("td", {}, ROLE_LABELS[u.role] || u.role),
                      h("td", {}, u.department.name),
                      h("td", {}, u.position?.name || "—"),
                      h("td", {}, h("span", { class: `status ${u.is_active ? "status-active" : "status-inactive"}` }, u.is_active ? "активен" : "деактивирован")),
                      h(
                        "td",
                        { class: "actions-cell" },
                        h(
                          "div",
                          { class: "row-actions" },
                          can("user:edit") && h("button", { class: "btn btn-sm", type: "button", onclick: (e) => editUser(u.id, e.currentTarget, () => load()) }, "Изменить"),
                          can("user:deactivate") &&
                            u.is_active &&
                            u.id !== session.me.id &&
                            h("button", { class: "btn btn-sm btn-danger", type: "button", onclick: (e) => deactivateUser(u, e.currentTarget, () => load()) }, "Деактивировать"),
                        ),
                      ),
                    ),
                  ),
                ),
              )
            : emptyBox("Пользователей по заданным условиям нет."),
        );
        pagerBox.replaceChildren(
          pager(
            data,
            (page) => {
              st.page = page;
              load();
            },
            (size) => {
              st.page_size = size;
              st.page = 1;
              load();
            },
          ),
        );
      },
    );
  }
  await load();
}

/* ==========================================================================
   Справочники (администратор)
   ========================================================================== */

const DICTIONARIES = [
  { key: "departments", title: "Подразделения", single: "подразделение", client: () => api.departments, cacheKey: "departments" },
  { key: "positions", title: "Должности", single: "должность", client: () => api.positions, cacheKey: "positions" },
  { key: "types", title: "Типы документов", single: "тип документа", client: () => api.documentTypes, cacheKey: "types", toggle: true },
];

function openRenameForm(dict, item, onSaved) {
  const submit = h("button", { class: "btn btn-primary", type: "submit" }, "Сохранить");
  const form = h(
    "form",
    { novalidate: true },
    field({ label: "Название", name: "name", required: true, value: item.name, attrs: { minlength: 2, maxlength: 255 } }),
    h("div", { class: "form-actions" }, submit, h("button", { class: "btn", type: "button", onclick: () => close() }, "Отмена")),
  );
  const close = openModal({ title: `Переименовать ${dict.single}`, body: form });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!validateForm(form)) return;
    await withBusy(submit, async () => {
      try {
        const saved = await dict.client().update(item.id, { name: form.name.value.trim() });
        dropCache(dict.cacheKey);
        toast(saved.name, { type: "success", title: "Название сохранено" });
        close();
        onSaved();
      } catch (error) {
        handleError(error, { form });
      }
    });
  });
}

function dictionaryPanel(panel, dict) {
  const add = h("button", { class: "btn btn-primary", type: "submit" }, "Добавить");
  const form = h(
    "form",
    { class: "filters", novalidate: true, style: "grid-template-columns: minmax(240px, 1fr) auto" },
    field({ label: "Новая запись", name: "name", required: true, attrs: { minlength: 2, maxlength: 255, placeholder: "Название" } }),
    h("div", { class: "filter-actions" }, add),
  );
  const tableBox = h("div", { class: "table-wrap" });
  panel.append(form, tableBox);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!validateForm(form)) return;
    await withBusy(add, async () => {
      try {
        const created = await dict.client().create({ name: form.name.value.trim() });
        dropCache(dict.cacheKey);
        form.name.value = "";
        toast(created.name, { type: "success", title: "Запись добавлена" });
        load();
      } catch (error) {
        handleError(error, { form });
      }
    });
  });

  async function toggle(item, button) {
    await withBusy(button, async () => {
      try {
        await api.documentTypes.update(item.id, { is_active: !item.is_active });
        dropCache("types");
        toast(item.name, { type: "success", title: item.is_active ? "Тип выведен из использования" : "Тип возвращён в использование" });
        load();
      } catch (error) {
        handleError(error);
      }
    });
  }

  function load() {
    return loadInto(
      tableBox,
      () => dict.client().list(),
      (items) => {
        if (!items.length) {
          tableBox.replaceChildren(emptyBox("Записей нет. Добавьте первую запись."));
          return;
        }
        const headers = dict.toggle ? ["Название", "Состояние", ""] : ["Название", ""];
        tableBox.replaceChildren(
          h(
            "table",
            {},
            h("caption", { class: "sr-only" }, dict.title),
            h("thead", {}, h("tr", {}, headers.map((t) => h("th", { scope: "col" }, t)))),
            h(
              "tbody",
              {},
              items.map((item) =>
                h(
                  "tr",
                  {},
                  h("td", {}, item.name),
                  dict.toggle &&
                    h("td", {}, h("span", { class: `status ${item.is_active ? "status-active" : "status-inactive"}` }, item.is_active ? "используется" : "не используется")),
                  h(
                    "td",
                    { class: "actions-cell" },
                    h("button", { class: "btn btn-sm", type: "button", onclick: () => openRenameForm(dict, item, () => load()) }, "Переименовать"),
                    dict.toggle && " ",
                    dict.toggle &&
                      h("button", { class: "btn btn-sm", type: "button", onclick: (e) => toggle(item, e.currentTarget) }, item.is_active ? "Вывести из использования" : "Вернуть в использование"),
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
  load();
}

async function viewDictionaries(content, { params }) {
  content.append(pageHead("Справочники", "Значения, из которых выбирают при регистрации документов и учётных записей."));
  const requested = params.get("tab");
  let active = DICTIONARIES.some((d) => d.key === requested) ? requested : DICTIONARIES[0].key;
  const panel = h("div", { id: "dict-panel", role: "tabpanel", class: "narrow" });
  const buttons = DICTIONARIES.map((d) =>
    h("button", { type: "button", role: "tab", id: `dict-tab-${d.key}`, "aria-controls": "dict-panel", onclick: () => select(d.key) }, d.title),
  );
  content.append(h("div", { class: "tabs", role: "tablist", "aria-label": "Справочники" }, buttons), panel);
  function select(key) {
    active = key;
    for (const b of buttons) b.setAttribute("aria-selected", String(b.id === `dict-tab-${key}`));
    panel.setAttribute("aria-labelledby", `dict-tab-${key}`);
    history.replaceState(null, "", `#/dictionaries?tab=${key}`);
    panel.replaceChildren();
    dictionaryPanel(
      panel,
      DICTIONARIES.find((d) => d.key === key),
    );
  }
  select(active);
}

/* ==========================================================================
   Запуск
   ========================================================================== */

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
else boot();
