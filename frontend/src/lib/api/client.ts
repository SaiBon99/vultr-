import { readSse } from "./sse";
import {
  ApiError,
  type ChatEvent,
  type ReviewApi,
  type RunLogLine,
} from "./types";

export interface ClientOptions {
  baseUrl: string;
  /** Called per request so the token can change after sign-in. */
  getToken: () => string | null;
  fetch?: typeof fetch;
}

/** Live adapter: typed fetch against the FastAPI proxy, reviewer token in X-Reviewer-Token. */
export function createLiveApi({
  baseUrl,
  getToken,
  fetch: f = fetch,
}: ClientOptions): ReviewApi {
  const root = baseUrl.replace(/\/+$/, "");

  async function send(
    path: string,
    init: RequestInit = {},
    accept = "application/json",
  ): Promise<Response> {
    const headers = new Headers(init.headers);
    headers.set("Accept", accept);
    if (init.body) headers.set("Content-Type", "application/json");
    const token = getToken();
    if (token) headers.set("X-Reviewer-Token", token);
    const res = await f(`${root}${path}`, { ...init, headers });
    if (!res.ok) {
      const err = (await res.json().catch(() => null)) as {
        detail?: unknown;
        code?: string;
        run_id?: string;
      } | null;
      throw new ApiError(
        res.status,
        typeof err?.detail === "string" ? err.detail : res.statusText,
        err?.code,
        err?.run_id,
      );
    }
    return res;
  }

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    return (await (await send(path, init)).json()) as T;
  }

  const qs = (params: Record<string, string | undefined>) => {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) p.set(k, v);
    const s = p.toString();
    return s ? `?${s}` : "";
  };

  async function* streamChat(
    chatId: string,
    message: string,
    signal?: AbortSignal,
  ): AsyncGenerator<ChatEvent> {
    const res = await send(
      `/chat/${encodeURIComponent(chatId)}/messages`,
      { method: "POST", body: JSON.stringify({ message }), signal },
      "text/event-stream",
    );
    if (!res.body)
      throw new ApiError(res.status, "The chat stream had no body");
    for await (const data of readSse(res.body)) yield parseChatEvent(data);
  }

  return {
    getHealth: () => request("/health"),
    listQuarantine: (status) => request(`/quarantine${qs({ status })}`),
    decide: (id, body) =>
      request(`/quarantine/${encodeURIComponent(id)}/decide`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    getAudit: (sessionId) => request(`/audit${qs({ session_id: sessionId })}`),
    getPublicKey: () => request("/keys/public"),
    getReceipt: (id) => request(`/receipts/${encodeURIComponent(id)}`),
    crawl: (body) =>
      request("/crawl", { method: "POST", body: JSON.stringify(body) }),
    getCrawlRunLog: async (runId) => {
      const res = await send(
        `/crawl/runs/${encodeURIComponent(runId)}/log`,
        {},
        "application/x-ndjson",
      );
      return parseRunLog(await res.text());
    },
    createChat: () => request("/chat/sessions", { method: "POST" }),
    sendChatMessage: (chatId, message, options) =>
      streamChat(chatId, message, options?.signal),
    getChatRunLog: async (runId) => {
      const res = await send(
        `/chat/runs/${encodeURIComponent(runId)}/log`,
        {},
        "application/x-ndjson",
      );
      return parseRunLog(await res.text());
    },
  };
}

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === "number";

/** True when `v` has the discriminant and the fields the viewer reads for its line type. */
function isRunLogLine(v: unknown): v is RunLogLine {
  if (!isRecord(v)) return false;
  switch (v.type) {
    case "run_start":
      return typeof v.run_id === "string";
    case "msg":
      return (
        isNum(v.seq) &&
        isNum(v.t_ms) &&
        (v.dir === "host_to_agent" || v.dir === "agent_to_host") &&
        (isRecord(v.msg) || typeof v.raw === "string")
      );
    case "host":
      return isNum(v.seq) && isNum(v.t_ms) && typeof v.event === "string";
    case "run_end":
      return v.status === "ok" || v.status === "error";
    default:
      return false;
  }
}

/**
 * Parse a run log (NDJSON, wire rule 6) into one object per non-empty line.
 * Throws on a line that is not JSON or not a known line type.
 * shortcut: checks only the fields the viewer reads, add a full schema check if the log feeds logic.
 */
export function parseRunLog(text: string): RunLogLine[] {
  const lines: RunLogLine[] = [];
  text.split(/\r?\n/).forEach((line, i) => {
    if (!line.trim()) return;
    let value: unknown;
    try {
      value = JSON.parse(line);
    } catch {
      throw new Error(`Run log line ${i + 1} is not valid JSON`);
    }
    if (!isRunLogLine(value))
      throw new Error(`Run log line ${i + 1} is not a known line type`);
    lines.push(value);
  });
  return lines;
}

const CHAT_EVENT_TYPES = new Set(["run", "step", "reply", "error", "done"]);

/**
 * Parse one SSE data payload into a ChatEvent. Throws on non-JSON or an unknown type.
 * shortcut: checks the discriminant only; the host validates events against the contract.
 */
export function parseChatEvent(data: string): ChatEvent {
  let value: unknown;
  try {
    value = JSON.parse(data);
  } catch {
    throw new Error("A chat stream event is not valid JSON");
  }
  if (!isRecord(value) || !CHAT_EVENT_TYPES.has(value.type as string))
    throw new Error("A chat stream event has an unknown type");
  return value as unknown as ChatEvent;
}
