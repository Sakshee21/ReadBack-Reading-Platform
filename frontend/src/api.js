const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

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

  startSession: (bookId, microSessionId) =>
    request("/sessions/start", { method: "POST", body: { book_id: bookId, micro_session_id: microSessionId } }),
  completeSession: (sessionId) =>
    request("/sessions/complete", { method: "POST", body: { session_id: sessionId } }),

  submitCheckpoint: (checkpointId, answers) =>
    request("/checkpoints/submit", { method: "POST", body: { checkpoint_id: checkpointId, answers } }),

  getStreak: () => request("/streaks/me"),
};

export { ApiError };
