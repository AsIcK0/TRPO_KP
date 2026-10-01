/**
 * HTTP-клиент REST API (/api/v1).
 *
 * - JWT хранится в localStorage (пароль нигде не сохраняется) и подставляется
 *   в заголовок Authorization: Bearer ... для каждого запроса.
 * - Ошибки backend приходят в едином формате {detail, code, field} и превращаются в ApiError.
 * - Ответ 401 очищает токен и вызывает обработчик, который показывает форму входа.
 */

const BASE = "/api/v1";
const TOKEN_KEY = "incoming-correspondence.jwt";

export class ApiError extends Error {
  constructor(status, body = {}) {
    super(body.detail || `Ошибка ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code || null;
    this.field = body.field || null;
    this.detail = body.detail || null;
  }
}

let unauthorizedHandler = () => {};
let memoryToken = null; // запасной вариант, если localStorage недоступен

export const auth = {
  get token() {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  save(token) {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* localStorage недоступен (приватный режим): токен живет до перезагрузки страницы */
      memoryToken = token;
    }
  },
  clear() {
    memoryToken = null;
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ничего */
    }
  },
  onUnauthorized(handler) {
    unauthorizedHandler = handler;
  },
};

function currentToken() {
  return auth.token || memoryToken;
}

function buildUrl(path, query) {
  const url = new URL(BASE + path, window.location.origin);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
    }
  }
  return url.pathname + url.search;
}

async function parseError(response) {
  let body = {};
  try {
    body = await response.json();
  } catch {
    body = {};
  }
  if (typeof body.detail !== "string") {
    // на случай ответа не из нашего backend (прокси, 502 и т. п.)
    body = { detail: `Ошибка сервера (${response.status})`, code: "HTTP_ERROR" };
  }
  return new ApiError(response.status, body);
}

/** Имя файла из Content-Disposition: приоритет у filename* (UTF-8, кириллица). */
function filenameFrom(response, fallback) {
  const header = response.headers.get("Content-Disposition") || "";
  const star = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (star) {
    try {
      return decodeURIComponent(star[1]);
    } catch {
      /* падаем на обычное имя */
    }
  }
  const plain = header.match(/filename="?([^";]+)"?/i);
  return plain ? plain[1] : fallback;
}

/**
 * Базовый запрос.
 * @param {string} method
 * @param {string} path  путь относительно /api/v1
 * @param {{query?: object, json?: any, form?: FormData, blob?: boolean, redirectOn401?: boolean}} options
 */
async function request(method, path, { query, json, form, blob = false, redirectOn401 = true } = {}) {
  const headers = { Accept: blob ? "*/*" : "application/json" };
  const token = currentToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form) {
    body = form; // boundary multipart браузер проставит сам
  }

  let response;
  try {
    response = await fetch(buildUrl(path, query), { method, headers, body });
  } catch {
    throw new ApiError(0, { detail: "Сервер недоступен. Проверьте подключение и повторите.", code: "NETWORK_ERROR" });
  }

  if (!response.ok) {
    const error = await parseError(response);
    if (response.status === 401 && redirectOn401) {
      auth.clear();
      unauthorizedHandler(error);
    }
    throw error;
  }
  if (blob) {
    return { blob: await response.blob(), filename: filenameFrom(response, "download") };
  }
  if (response.status === 204) return null;
  return response.json();
}

const get = (path, query) => request("GET", path, { query });
const post = (path, json) => request("POST", path, { json });
const patch = (path, json) => request("PATCH", path, { json });

/** Все страницы списка (для выпадающих списков справочников). */
async function listAll(path, query = {}) {
  const items = [];
  for (let page = 1; ; page += 1) {
    const data = await get(path, { ...query, page, page_size: 100 });
    items.push(...data.items);
    if (page >= data.pages || data.items.length === 0) return items;
  }
}

export const api = {
  // --- авторизация ---
  login: (login, password) => request("POST", "/auth/login", { json: { login, password }, redirectOn401: false }),
  me: () => get("/auth/me"),

  // --- входящие документы ---
  documents: {
    list: (query) => get("/incoming", query),
    get: (id) => get(`/incoming/${encodeURIComponent(id)}`),
    byNumber: (number) => get(`/incoming/by-registration-number/${encodeURIComponent(number)}`),
    create: (data) => post("/incoming", data),
    update: (id, data) => patch(`/incoming/${encodeURIComponent(id)}`, data),
    remove: (id) => request("DELETE", `/incoming/${encodeURIComponent(id)}`),
    changeStatus: (id, status, comment) => post(`/incoming/${encodeURIComponent(id)}/status`, { status, comment: comment || null }),
    history: (id) => get(`/incoming/${encodeURIComponent(id)}/history`),
    resolutions: (id) => get(`/incoming/${encodeURIComponent(id)}/resolutions`),
    createResolution: (id, data) => post(`/incoming/${encodeURIComponent(id)}/resolutions`, data),
    uploadFile: (id, file, attachmentType) => {
      const form = new FormData();
      form.append("file", file, file.name);
      if (attachmentType) form.append("attachment_type", attachmentType);
      return request("POST", `/incoming/${encodeURIComponent(id)}/files`, { form });
    },
  },
  resolutions: {
    update: (id, data) => patch(`/resolutions/${encodeURIComponent(id)}`, data),
  },
  files: {
    download: (id) => request("GET", `/files/${encodeURIComponent(id)}/download`, { blob: true }),
  },

  // --- корреспонденты ---
  correspondents: {
    list: (query) => get("/correspondents", query),
    all: () => listAll("/correspondents"),
    get: (id) => get(`/correspondents/${encodeURIComponent(id)}`),
    create: (data) => post("/correspondents", data),
    update: (id, data) => patch(`/correspondents/${encodeURIComponent(id)}`, data),
  },

  // --- справочники ---
  documentTypes: {
    list: () => get("/document-types"),
    create: (data) => post("/document-types", data),
    update: (id, data) => patch(`/document-types/${encodeURIComponent(id)}`, data),
  },
  departments: {
    list: () => get("/departments"),
    create: (data) => post("/departments", data),
    update: (id, data) => patch(`/departments/${encodeURIComponent(id)}`, data),
  },
  positions: {
    list: () => get("/positions"),
    create: (data) => post("/positions", data),
    update: (id, data) => patch(`/positions/${encodeURIComponent(id)}`, data),
  },

  // --- пользователи ---
  users: {
    list: (query) => get("/users", query),
    get: (id) => get(`/users/${encodeURIComponent(id)}`),
    create: (data) => post("/users", data),
    update: (id, data) => patch(`/users/${encodeURIComponent(id)}`, data),
    deactivate: (id) => post(`/users/${encodeURIComponent(id)}/deactivate`),
    executors: () => get("/users/executors"),
  },

  // --- отчеты и выгрузка ---
  reports: {
    generate: (payload) => request("POST", "/reports/generate", { json: payload, blob: true }),
  },
  exports: {
    registrationLog: (query) => request("GET", "/exports/registration-log", { query, blob: true }),
  },
};

/** Сохранить полученный файл на диск пользователя. */
export function saveBlob({ blob, filename }) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}
