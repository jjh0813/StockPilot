const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const answerOutput = document.querySelector("#answerOutput");
const eventTimeline = document.querySelector("#eventTimeline");
const toolBadge = document.querySelector("#toolBadge");
const apiStatus = document.querySelector("#apiStatus");
const statusDot = document.querySelector(".dot");
const scenarioButtons = document.querySelectorAll(".scenario");

const sessionId = `demo-${Date.now()}`;
let activeController = null;

scenarioButtons.forEach((button) => {
  button.addEventListener("click", () => {
    input.value = button.dataset.message;
    input.focus();
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  await streamChat(message);
});

async function streamChat(message) {
  if (activeController) {
    activeController.abort();
  }

  activeController = new AbortController();
  setBusy(true);
  resetOutput();
  addEvent("요청 전송", "FastAPI /api/v1/chat/stream으로 질문을 보냅니다.");

  try {
    const response = await fetch("/api/v1/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        session_id: sessionId,
      }),
      signal: activeController.signal,
    });

    if (!response.ok || !response.body) {
      throw new Error(`HTTP ${response.status}`);
    }

    await readSseStream(response.body);
  } catch (error) {
    if (error.name !== "AbortError") {
      addEvent("오류", error.message || "요청 실패", "error");
      answerOutput.textContent = "요청 처리 중 오류가 발생했습니다. 서버와 .env 값을 확인하세요.";
    }
  } finally {
    setBusy(false);
    activeController = null;
  }
}

async function readSseStream(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const event = parseSseEvent(part);
      if (event) handleStreamEvent(event);
    }
  }

  if (buffer.trim()) {
    const event = parseSseEvent(buffer);
    if (event) handleStreamEvent(event);
  }
}

function parseSseEvent(raw) {
  const dataLine = raw
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.startsWith("data:"));

  if (!dataLine) return null;

  try {
    return JSON.parse(dataLine.slice("data:".length).trim());
  } catch {
    return null;
  }
}

function handleStreamEvent(event) {
  switch (event.type) {
    case "thinking":
      addEvent(`thinking · ${event.node || "graph"}`, event.content || "진행 중");
      break;
    case "tool":
      toolBadge.textContent = `tool: ${event.tool_name || "-"}`;
      addEvent("tool 실행", event.tool_name || "도구 실행");
      break;
    case "token":
      if (answerOutput.dataset.empty === "true") {
        answerOutput.textContent = "";
        answerOutput.dataset.empty = "false";
      }
      answerOutput.textContent += event.content || "";
      break;
    case "response":
      if (event.tool_used) {
        toolBadge.textContent = `tool: ${event.tool_used}`;
      }
      if (event.content) {
        answerOutput.textContent = event.content;
        answerOutput.dataset.empty = "false";
      }
      addEvent("response", event.content ? "최종 답변 수신" : "토큰 스트림 완료");
      break;
    case "error":
      addEvent("error", event.error || "알 수 없는 오류", "error");
      answerOutput.textContent = event.error || "오류가 발생했습니다.";
      break;
    case "done":
      addEvent("done", "SSE 스트림 종료", "done");
      break;
    default:
      addEvent(event.type || "event", JSON.stringify(event));
  }
}

function resetOutput() {
  answerOutput.textContent = "답변 생성 중...";
  answerOutput.dataset.empty = "true";
  toolBadge.textContent = "tool: -";
  eventTimeline.innerHTML = "";
}

function addEvent(title, content, className = "") {
  const item = document.createElement("li");
  if (className) item.classList.add(className);
  item.innerHTML = `<strong>${escapeHtml(title)}</strong>${escapeHtml(content)}`;
  eventTimeline.appendChild(item);
  eventTimeline.scrollTop = eventTimeline.scrollHeight;
}

function setBusy(isBusy) {
  sendButton.disabled = isBusy;
  sendButton.textContent = isBusy ? "분석 중..." : "분석 시작";
  apiStatus.textContent = isBusy ? "SSE 스트리밍 중" : "서버 연결 가능";
  statusDot.classList.toggle("ok", !isBusy);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

apiStatus.textContent = "서버 연결 가능";
statusDot.classList.add("ok");
