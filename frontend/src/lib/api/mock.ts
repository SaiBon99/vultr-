import audit from "../../../../contracts/fixtures/audit.json";
import chatSessionJson from "../../../../contracts/fixtures/chat_session.json";
import chatStreamJson from "../../../../contracts/fixtures/chat_stream.json";
import health from "../../../../contracts/fixtures/health.json";
import keys from "../../../../contracts/fixtures/keys_public.json";
import quarantine from "../../../../contracts/fixtures/quarantine.json";
import receiptJson from "../../../../contracts/fixtures/receipts/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3.json";
import { sha256Hex } from "../crypto/auditChain";
import { canonBytes } from "../crypto/canonical";
import { RULEBOOK, sortQueue } from "../review";
import {
  CHAT_DELAY_MS,
  chatJudgeNotes,
  JUDGE_DELAY_MS,
  pendingItem,
  pendingResolved,
  triageSession,
} from "./mockData";
import {
  ApiError,
  type AuditLog,
  type ChatEvent,
  type ChatRememberDetail,
  type ChatSession,
  type ChatStepEvent,
  type CrawlLimits,
  type Health,
  type PublicKey,
  type QuarantineItem,
  type QuarantineList,
  type Receipt,
  type ReviewApi,
  type RunLogLine,
} from "./types";

const clone = <T>(v: unknown): T => structuredClone(v) as T;
const fixtureReceipt = receiptJson as unknown as Receipt;
const MOCK_LIMITS: CrawlLimits = { memory_mb: 512, cpus: 1, timeout_s: 30 };
const MOCK_IMAGE = "sha256:" + "0".repeat(64);
const MOCK_CONTAINER = "0".repeat(64);

/** Mock-only trigger: a URL whose host ends in .invalid fails like a real fetch_failed run. */
const isFailingUrl = (url: string): boolean => {
  try {
    return new URL(url).hostname.endsWith(".invalid");
  } catch {
    return false;
  }
};

/** Short sample transcripts (wire rule 6) for a successful and a failed crawl. */
export function mockRunLog(
  runId: string,
  url: string,
  ok: boolean,
): RunLogLine[] {
  const start: RunLogLine = {
    type: "run_start",
    run_id: runId,
    kind: "crawl",
    session_id: null,
    started_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
    limits: MOCK_LIMITS,
    image_id: MOCK_IMAGE,
  };
  const head: RunLogLine[] = [
    start,
    {
      type: "msg",
      seq: 1,
      t_ms: 3,
      dir: "host_to_agent",
      msg: { type: "task", url },
    },
    {
      type: "msg",
      seq: 2,
      t_ms: 410,
      dir: "agent_to_host",
      msg: { type: "fetch", url },
    },
  ];
  if (!ok)
    return [
      ...head,
      {
        type: "host",
        seq: 3,
        t_ms: 690,
        event: "fetch",
        final_url: url,
        error_code: "fetch_failed",
      },
      {
        type: "run_end",
        status: "error",
        http_status: 502,
        error_code: "fetch_failed",
        exit_code: null,
        container_id: MOCK_CONTAINER,
        elapsed_ms: 720,
        stderr: "",
        stderr_truncated: false,
        lines_dropped: 0,
      },
    ];
  const body = `<html><head><title>Mock page</title></head><body>${"Mock body text. ".repeat(40)}</body></html>`;
  return [
    ...head,
    {
      type: "host",
      seq: 3,
      t_ms: 690,
      event: "fetch",
      final_url: url,
      status: 200,
      bytes: body.length,
      content_type: "text/html",
    },
    {
      type: "msg",
      seq: 4,
      t_ms: 691,
      dir: "host_to_agent",
      msg: {
        type: "fetch_result",
        final_url: url,
        content_type: "text/html",
        body,
        body_truncated: false,
      },
    },
    {
      type: "host",
      seq: 5,
      t_ms: 1980,
      event: "model",
      model: "mock",
      inference_id: "mock-inference",
      usage: null,
      latency_ms: 1255,
    },
    {
      type: "msg",
      seq: 6,
      t_ms: 1990,
      dir: "agent_to_host",
      msg: {
        type: "result",
        title: "Mock page",
        summary: "Canned crawl result.",
        key_points: ["Mock data"],
      },
    },
    {
      type: "run_end",
      status: "ok",
      http_status: 200,
      error_code: null,
      exit_code: 0,
      container_id: MOCK_CONTAINER,
      elapsed_ms: 2100,
      stderr: "",
      stderr_truncated: false,
      lines_dropped: 0,
    },
  ];
}

/** Short sample transcript (wire rule 6) for a replayed chat message. */
export function mockChatRunLog(
  runId: string,
  sessionId: string,
  message: string,
  events: ChatEvent[],
): RunLogLine[] {
  const run = events.find((e) => e.type === "run");
  const steps = events.filter((e): e is ChatStepEvent => e.type === "step");
  let seq = 0;
  let t = 0;
  const next = () => ({ seq: ++seq, t_ms: (t += 420) });
  const lines: RunLogLine[] = [
    {
      type: "run_start",
      run_id: runId,
      kind: "chat",
      session_id: sessionId,
      started_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
      limits: run?.type === "run" ? run.limits : MOCK_LIMITS,
      image_id: MOCK_IMAGE,
    },
    {
      type: "msg",
      ...next(),
      dir: "host_to_agent",
      msg: { type: "task", message },
    },
  ];
  for (const step of steps)
    lines.push(
      {
        type: "msg",
        ...next(),
        dir: "agent_to_host",
        msg: { type: "tool_call", tool: step.tool, index: step.index },
      },
      {
        type: "host",
        ...next(),
        event: step.tool,
        status: step.status,
        ...(step.error_code ? { error_code: step.error_code } : {}),
      },
    );
  lines.push(
    { type: "msg", ...next(), dir: "agent_to_host", msg: { type: "reply" } },
    {
      type: "run_end",
      status: "ok",
      http_status: 200,
      error_code: null,
      exit_code: 0,
      container_id: MOCK_CONTAINER,
      elapsed_ms: t + 100,
      stderr: "",
      stderr_truncated: false,
      lines_dropped: 0,
    },
  );
  return lines;
}

const randomDelay = () =>
  CHAT_DELAY_MS.min + Math.random() * (CHAT_DELAY_MS.max - CHAT_DELAY_MS.min);

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason);
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(signal.reason);
      },
      { once: true },
    );
  });
}

const microTime = () =>
  new Date().toISOString().replace(/\.(\d{3})Z$/, ".$1000Z");

function toBase64(buf: ArrayBuffer): string {
  let bin = "";
  for (const b of new Uint8Array(buf)) bin += String.fromCharCode(b);
  return btoa(bin);
}

interface Signer {
  key: PublicKey;
  sign: (
    unsigned: Omit<Receipt, "signature_b64" | "key_id">,
  ) => Promise<Receipt>;
}

/**
 * Ephemeral Ed25519 key made in this tab, so mock receipts are signed for the real decision
 * and the browser verification path runs for real. Falls back to the fixture key and receipt
 * where Web Crypto lacks Ed25519.
 */
async function createSigner(): Promise<Signer | null> {
  try {
    const pair = (await crypto.subtle.generateKey({ name: "Ed25519" }, true, [
      "sign",
      "verify",
    ])) as CryptoKeyPair;
    const raw = await crypto.subtle.exportKey("raw", pair.publicKey);
    const jwk = await crypto.subtle.exportKey("jwk", pair.publicKey);
    const keyIdDigest = await crypto.subtle.digest("SHA-256", raw);
    const key_id = Array.from(new Uint8Array(keyIdDigest), (b) =>
      b.toString(16).padStart(2, "0"),
    )
      .join("")
      .slice(0, 16);
    const key: PublicKey = {
      alg: "Ed25519",
      key_id,
      public_key_b64: toBase64(raw),
      jwk: { kty: "OKP", crv: "Ed25519", x: jwk.x ?? "" },
    };
    return {
      key,
      sign: async (unsigned) => {
        const body = { ...unsigned, key_id };
        const sig = await crypto.subtle.sign(
          "Ed25519",
          pair.privateKey,
          canonBytes(body),
        );
        return { ...body, signature_b64: toBase64(sig) };
      },
    };
  } catch {
    return null;
  }
}

export interface MockOptions {
  /** How long the pending judge row stays pending. */
  judgeDelayMs?: number;
  /** Pause before each replayed chat event; 500 to 900 ms by default. */
  chatDelayMs?: () => number;
}

/** Mock adapter: serves ../contracts/fixtures plus mockData rows, applies decisions in memory. */
export function createMockApi({
  judgeDelayMs = JUDGE_DELAY_MS,
  chatDelayMs = randomDelay,
}: MockOptions = {}): ReviewApi {
  const base = clone<QuarantineList>(quarantine);
  base.sessions[0].items.push(clone<QuarantineItem>(pendingItem));
  base.sessions[0].write_count += 1;
  base.sessions.push(clone(triageSession));
  const state = sortQueue(base);
  const runLogs = new Map<string, RunLogLine[]>();
  const started = Date.now();
  const receipts = new Map<string, Receipt>();
  let signer: Promise<Signer | null> | undefined;
  const chats = new Map<string, ChatSession & { busy: boolean }>();

  const items = () => state.sessions.flatMap((s) => s.items);
  const find = (id: string) => items().find((i) => i.id === id);

  function receiptFor(
    item: QuarantineItem,
  ): Omit<Receipt, "signature_b64" | "key_id"> {
    return {
      receipt_id: item.receipt_id ?? crypto.randomUUID(),
      event: item.status === "purged" ? "purged" : "overridden",
      quarantine_id: item.id,
      session_id: item.session_id,
      verdict: item.verdict,
      risk_score: item.risk_score,
      rule_flags: item.rule_flags,
      payload_hash: item.payload_hash,
      audit_head_hash: audit.head_hash,
      override_reason: item.override_reason,
      timestamp: (item.decided_at ?? microTime()).replace(/\.\d+Z$/, "Z"),
      signature_alg: "Ed25519",
    };
  }

  /** Signs receipts for rows that arrive already decided, once the key exists. */
  function getSigner(): Promise<Signer | null> {
    signer ??= createSigner().then(async (s) => {
      if (s)
        for (const item of items())
          if (item.receipt_id)
            receipts.set(item.receipt_id, await s.sign(receiptFor(item)));
      return s;
    });
    return signer;
  }

  function resolveJudge() {
    if (Date.now() - started < judgeDelayMs) return;
    const row = find(pendingItem.id);
    if (row?.judge_status === "pending") {
      Object.assign(row, clone(pendingResolved));
      state.sessions = sortQueue(state).sessions;
    }
  }

  /** Adds a frozen chat write to the queue so its review link opens a real row. */
  function freeze(
    chat: ChatSession,
    d: ChatRememberDetail,
    sourceRef: string | null,
  ) {
    if (d.verdict === "ALLOW") return;
    let group = state.sessions.find((s) => s.session_id === chat.session_id);
    if (!group) {
      group = {
        session_id: chat.session_id,
        label: "Shopping chat",
        gate_mode: "quarantined",
        tainted: true,
        external_sources: sourceRef
          ? [
              {
                source_ref: sourceRef,
                source_kind: "web",
                read_at: microTime(),
              },
            ]
          : [],
        write_count: 0,
        created_at: chat.created_at,
        items: [],
      };
      state.sessions.push(group);
    }
    group.write_count += 1;
    const note = clone(
      chatJudgeNotes[d.verdict],
    ) as (typeof chatJudgeNotes)[keyof typeof chatJudgeNotes];
    const when = RULEBOOK.judge_boost_when;
    const boosted =
      note.recommended_action === when.recommended_action &&
      (when.risk_level as readonly string[]).includes(note.risk_level);
    group.items.push({
      id: d.id,
      session_id: chat.session_id,
      status: "quarantined",
      content: d.content,
      payload_hash: d.payload_hash,
      source: "external",
      source_ref: sourceRef,
      source_snippet: null,
      verdict: d.verdict,
      risk_score: d.risk_score,
      effective_priority_score:
        d.risk_score + (boosted ? RULEBOOK.judge_priority_boost : 0),
      rule_flags: d.rule_flags,
      judge_status: "done",
      judge_note: note,
      override_reason: null,
      decided_by: null,
      decided_at: null,
      receipt_uri: null,
      receipt_id: null,
      created_at: microTime(),
    });
    state.sessions = sortQueue(state).sessions;
  }

  /** Replays chat_stream.json with fresh run and row ids, one event per chatDelayMs. */
  async function* replayChat(
    chatId: string,
    message: string,
    signal?: AbortSignal,
  ): AsyncGenerator<ChatEvent> {
    const chat = chats.get(chatId);
    if (!chat) throw new ApiError(404, "Unknown chat", "chat_not_found");
    if (!message.trim() || message.length > 2000)
      throw new ApiError(
        422,
        "A message must be 1 to 2000 characters",
        "validation_error",
      );
    if (chat.busy)
      throw new ApiError(
        409,
        "This chat already has a message running",
        "chat_busy",
      );
    chat.busy = true;
    const runId = crypto.randomUUID();
    const events = clone<ChatEvent[]>(chatStreamJson);
    let browsed: string | null = null;
    try {
      for (const ev of events) {
        await wait(chatDelayMs(), signal);
        if (ev.type === "run") ev.chat_id = chatId;
        if (ev.type === "run" || ev.type === "error" || ev.type === "done")
          ev.run_id = runId;
        if (ev.type === "step" && ev.detail?.kind === "browse")
          browsed = ev.detail.final_url ?? ev.detail.url;
        if (ev.type === "step" && ev.detail?.kind === "remember") {
          ev.detail.id = crypto.randomUUID();
          if (ev.detail.table === "quarantine_queue")
            freeze(chat, ev.detail, browsed);
        }
        if (ev.type === "done") {
          ev.log_uri = `s3://mock-receipts/logs/chat/${runId}.jsonl`;
          runLogs.set(
            runId,
            mockChatRunLog(runId, chat.session_id, message, events),
          );
        }
        yield ev;
      }
    } finally {
      chat.busy = false;
    }
  }

  return {
    getHealth: async () => clone<Health>(health),
    listQuarantine: async (status) => {
      resolveJudge();
      const list = clone<QuarantineList>(state);
      if (!status) return list;
      return sortQueue({
        sessions: list.sessions
          .map((s) => ({
            ...s,
            items: s.items.filter((i) => i.status === status),
          }))
          .filter((s) => s.items.length > 0),
      });
    },
    decide: async (id, body) => {
      const item = find(id);
      if (!item) throw new ApiError(404, "Not found");
      if (item.status !== "quarantined")
        throw new ApiError(409, "Row already decided", "already_decided");
      if (
        body.action === "override" &&
        (item.verdict === "BLOCKED" || item.verdict === "FAIL_CLOSED") &&
        !body.reason?.trim()
      ) {
        throw new ApiError(
          422,
          "A reason is required to override a blocked row",
          "reason_required",
        );
      }
      if (
        body.action === "override" &&
        `sha256:${await sha256Hex(item.content ?? "")}` !== item.payload_hash
      ) {
        throw new ApiError(
          409,
          "Content does not match payload_hash",
          "payload_hash_mismatch",
        );
      }
      const s = await getSigner();
      item.status = body.action === "purge" ? "purged" : "overridden";
      if (body.action === "purge") item.content = null;
      item.override_reason =
        body.action === "override" ? body.reason?.trim() || null : null;
      item.decided_by = "reviewer";
      item.decided_at = microTime();
      item.receipt_id = crypto.randomUUID();
      item.receipt_uri = `s3://quarantine-receipts/receipts/${item.receipt_id}.json`;
      const receipt = s
        ? await s.sign(receiptFor(item))
        : clone<Receipt>(fixtureReceipt);
      receipts.set(item.receipt_id, receipt);
      return {
        item: clone<QuarantineItem>(item),
        receipt: clone<Receipt>(receipt),
        memory_id: body.action === "override" ? crypto.randomUUID() : null,
      };
    },
    getAudit: async () => clone<AuditLog>(audit),
    getPublicKey: async () => {
      const s = await getSigner();
      return s ? clone<PublicKey>(s.key) : clone<PublicKey>(keys);
    },
    getReceipt: async (id) => {
      const s = await getSigner();
      const r = s
        ? receipts.get(id)
        : id === fixtureReceipt.receipt_id
          ? fixtureReceipt
          : undefined;
      if (!r) throw new ApiError(404, "Not found");
      return clone<Receipt>(r);
    },
    crawl: async (body) => {
      const runId = crypto.randomUUID();
      const ok = !isFailingUrl(body.url);
      runLogs.set(runId, mockRunLog(runId, body.url, ok));
      if (!ok)
        throw new ApiError(
          502,
          "Could not fetch the page",
          "fetch_failed",
          runId,
        );
      return {
        url: body.url,
        final_url: body.url,
        title: "Mock page",
        summary: "Canned crawl result. Mock mode does not run the sandbox.",
        key_points: ["Mock data", "No container was started"],
        model: "mock",
        inference_id: "mock-inference",
        usage: null,
        elapsed_ms: 0,
        sandbox: {
          runtime: "docker",
          container_id: MOCK_CONTAINER,
          image_id: MOCK_IMAGE,
          network: "none",
          limits: MOCK_LIMITS,
        },
        run_id: runId,
        log_uri: `s3://mock-receipts/logs/crawl/${runId}.jsonl`,
        pages: [
          {
            url: body.url,
            final_url: body.url,
            status: "ok",
            title: "Example Domain",
            error: null,
          },
        ],
      };
    },
    getCrawlRunLog: async (runId) => {
      const log = runLogs.get(runId);
      if (!log)
        throw new ApiError(404, "No transcript for this run", "not_found");
      return structuredClone(log);
    },
    createChat: async () => {
      const fixture = clone<ChatSession>(chatSessionJson);
      const chat: ChatSession = chats.has(fixture.chat_id)
        ? {
            chat_id: crypto.randomUUID(),
            session_id: crypto.randomUUID(),
            created_at: microTime(),
          }
        : fixture;
      chats.set(chat.chat_id, { ...chat, busy: false });
      return clone<ChatSession>(chat);
    },
    sendChatMessage: (chatId, message, options) =>
      replayChat(chatId, message, options?.signal),
    getChatRunLog: async (runId) => {
      const log = runLogs.get(runId);
      if (!log)
        throw new ApiError(404, "No transcript for this run", "not_found");
      return structuredClone(log);
    },
  };
}
