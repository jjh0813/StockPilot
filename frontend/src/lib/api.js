// 백엔드 API 클라이언트
const API_BASE = "http://127.0.0.1:8000/api/v1";
const TOKEN_KEY = "stockpilot_token";
const USER_KEY = "stockpilot_user";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function getUsername() {
  return localStorage.getItem(USER_KEY);
}
export function setAuth(token, username) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, username || "");
  } else {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }
}

async function jsonFetch(path, { method = "GET", body, auth = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `요청 실패 (${res.status})`);
  }
  return data;
}

// ── 인증 ──────────────────────────────
export async function registerUser(username, password) {
  const data = await jsonFetch("/auth/register", {
    method: "POST",
    body: { username, password },
  });
  setAuth(data.access_token, data.username);
  return data;
}
export async function loginUser(username, password) {
  const data = await jsonFetch("/auth/login", {
    method: "POST",
    body: { username, password },
  });
  setAuth(data.access_token, data.username);
  return data;
}

// ── 즐겨찾기 ──────────────────────────
export async function fetchWatchlist() {
  return jsonFetch("/watchlist/", { auth: true });
}
export async function addWatchlist(ticker, name) {
  return jsonFetch("/watchlist/", { method: "POST", body: { ticker, name }, auth: true });
}
export async function removeWatchlist(ticker) {
  return jsonFetch(`/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE", auth: true });
}

// ── 채팅 SSE 스트리밍 ──────────────────
export async function streamChat(message, { sessionId = "web", onEvent, signal } = {}) {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`서버 오류 (${res.status})`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data:")) continue;
      try {
        onEvent(JSON.parse(line.slice(5).trim()));
      } catch {
        // 무시
      }
    }
  }
}
