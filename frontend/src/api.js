export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const TOKEN_KEY = "readback_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const resp = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const data = await resp.json();
      detail = data.detail || detail;
    } catch {
      // response had no JSON body
    }
    throw new ApiError(detail, resp.status);
  }

  if (resp.status === 204) return null;
  return resp.json();
}

export const api = {
  register: (email, password) =>
    request("/auth/register", { method: "POST", body: { email, password }, auth: false }),
  login: (email, password) =>
    request("/auth/login", { method: "POST", body: { email, password }, auth: false }),
  me: () => request("/auth/me"),

  listBooks: () => request("/books"),
  getChapters: (bookId) => request(`/books/${bookId}`),
  getReaderPosition: (bookId) => request(`/books/${bookId}/reader`),
  getProgress: (bookId) => request(`/books/${bookId}/progress`),
  listMicroSessions: (bookId) => request(`/books/${bookId}/micro-sessions`),
  jumpToMicroSession: (bookId, microSessionId) =>
    request(`/books/${bookId}/jump`, { method: "POST", body: { micro_session_id: microSessionId } }),

  startSession: (bookId, microSessionId) =>
    request("/sessions/start", { method: "POST", body: { book_id: bookId, micro_session_id: microSessionId } }),
  completeSession: (sessionId) =>
    request("/sessions/complete", { method: "POST", body: { session_id: sessionId } }),

  submitCheckpoint: (checkpointId, answers) =>
    request("/checkpoints/submit", { method: "POST", body: { checkpoint_id: checkpointId, answers } }),

  getStreak: () => request("/streaks/me"),
  getPace: (bookId) => request(`/pace/me${bookId ? `?book_id=${bookId}` : ""}`),
  getNudge: () => request("/nudge/me"),

  getBookStatus: (bookId) => request(`/books/${bookId}/status`),
  deleteBook: (bookId) => request(`/books/${bookId}`, { method: "DELETE" }),
};

/**
 * Upload a book file. Uses XMLHttpRequest rather than fetch because only XHR
 * reports upload progress, and a 12MB EPUB over a slow connection needs a
 * progress bar. Returns the created book's {id, status, title}.
 */
export function uploadBook({ file, title, author, onProgress }) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    if (title) form.append("title", title);
    if (author) form.append("author", author);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/books/upload`);
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };

    xhr.onload = () => {
      let body = {};
      try {
        body = JSON.parse(xhr.responseText || "{}");
      } catch {
        // non-JSON error body
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new ApiError(body.detail || `Upload failed (${xhr.status})`, xhr.status));
    };
    xhr.onerror = () => reject(new ApiError("Network error during upload", 0));
    xhr.send(form);
  });
}

/**
 * Fire-and-forget instrumentation for the pilot. Known id fields are pulled
 * out into their own columns; everything else becomes the event's metadata.
 * Never throws - a failed log must not interrupt reading - but it warns rather
 * than failing silently, since missing pilot data is a real problem.
 */
export function logEvent(eventType, fields = {}) {
  const { bookId = null, chapterId = null, microSessionId = null, ...metadata } = fields;
  const body = {
    event_type: eventType,
    book_id: bookId,
    chapter_id: chapterId,
    micro_session_id: microSessionId,
    metadata: Object.keys(metadata).length ? metadata : null,
  };
  request("/events", { method: "POST", body }).catch((err) =>
    console.warn(`logEvent(${eventType}) failed:`, err.message)
  );
}

export { ApiError };
