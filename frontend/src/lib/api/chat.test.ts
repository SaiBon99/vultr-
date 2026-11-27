import { describe, expect, it } from "vitest";
import stream from "../../../../contracts/fixtures/chat_stream.json";
import { createLiveApi, parseChatEvent } from "./client";
import { createMockApi } from "./mock";
import { ApiError, type ChatEvent } from "./types";

async function collect(source: AsyncIterable<ChatEvent>): Promise<ChatEvent[]> {
  const out: ChatEvent[] = [];
  for await (const ev of source) out.push(ev);
  return out;
}

/** Serialises the fixture as an SSE body cut into 37-byte chunks, so lines split mid-way. */
function sseResponse(events: unknown[]): Response {
  const text = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  const bytes = new TextEncoder().encode(text);
  return new Response(
    new ReadableStream({
      start(c) {
        for (let i = 0; i < bytes.length; i += 37)
          c.enqueue(bytes.slice(i, i + 37));
        c.close();
      },
    }),
    { status: 200, headers: { "Content-Type": "text/event-stream" } },
  );
}

describe("live chat client", () => {
  it("POSTs the message and yields typed events in stream order", async () => {
    const calls: { url: string; init: RequestInit }[] = [];
    const api = createLiveApi({
      baseUrl: "http://host/",
      getToken: () => "tok",
      fetch: (async (url: string, init: RequestInit) => {
        calls.push({ url, init });
        return sseResponse(stream);
      }) as typeof fetch,
    });
    const events = await collect(api.sendChatMessage("abc", "Order paper"));
    expect(events.map((e) => e.type)).toEqual(
      (stream as { type: string }[]).map((e) => e.type),
    );
    expect(events).toEqual(stream);
    expect(calls[0].url).toBe("http://host/chat/abc/messages");
    expect(calls[0].init.method).toBe("POST");
    const headers = new Headers(calls[0].init.headers);
    expect(headers.get("Accept")).toBe("text/event-stream");
    expect(headers.get("X-Reviewer-Token")).toBe("tok");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      message: "Order paper",
    });
  });

  it.each([
    [404, "chat_not_found"],
    [409, "chat_busy"],
    [422, "validation_error"],
    [503, "sandbox_busy"],
  ])("throws ApiError %i %s before the stream starts", async (status, code) => {
    const api = createLiveApi({
      baseUrl: "",
      getToken: () => null,
      fetch: (async () =>
        new Response(JSON.stringify({ detail: "refused", code }), {
          status,
          headers: { "Content-Type": "application/json" },
        })) as typeof fetch,
    });
    const err = await collect(api.sendChatMessage("abc", "hi")).catch(
      (e: unknown) => e,
    );
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status, code, message: "refused" });
  });

  it("falls back to statusText when detail is not a string (FastAPI 422 list)", async () => {
    const api = createLiveApi({
      baseUrl: "",
      getToken: () => null,
      fetch: (async () =>
        new Response(JSON.stringify({ detail: [{ msg: "too long" }] }), {
          status: 422,
          statusText: "Unprocessable Entity",
        })) as typeof fetch,
    });
    await expect(collect(api.sendChatMessage("abc", "hi"))).rejects.toThrow(
      "Unprocessable Entity",
    );
  });

  it("rejects unknown event payloads", () => {
    expect(() => parseChatEvent("not json")).toThrow(/not valid JSON/);
    expect(() => parseChatEvent('{"type":"ping"}')).toThrow(/unknown type/);
    expect(parseChatEvent('{"type":"reply","text":"hi"}')).toEqual({
      type: "reply",
      text: "hi",
    });
  });
});

describe("mock chat replay", () => {
  it("replays the fixture, freezes non-ALLOW writes into the queue and stores a run log", async () => {
    const api = createMockApi({ judgeDelayMs: 60_000, chatDelayMs: () => 0 });
    const chat = await api.createChat();
    const events = await collect(
      api.sendChatMessage(chat.chat_id, "Order 2 reams"),
    );
    expect(events.map((e) => e.type)).toEqual(
      (stream as { type: string }[]).map((e) => e.type),
    );
    const run = events[0];
    expect(run).toMatchObject({ type: "run", chat_id: chat.chat_id });

    const frozen = events.flatMap((e) =>
      e.type === "step" && e.detail?.kind === "remember" ? [e.detail.id] : [],
    );
    const queue = await api.listQuarantine("quarantined");
    const group = queue.sessions.find((s) => s.session_id === chat.session_id);
    expect(group?.items.map((i) => i.id).sort()).toEqual([...frozen].sort());
    expect(group?.items[0].verdict).toBe("BLOCKED");

    const done = events.at(-1);
    if (done?.type !== "done") throw new Error("expected done last");
    const log = await api.getChatRunLog(done.run_id);
    expect(log[0]).toMatchObject({ type: "run_start", kind: "chat" });
    expect(log.at(-1)).toMatchObject({ type: "run_end", status: "ok" });
  });

  it("refuses an unknown chat and a second message while one runs", async () => {
    const api = createMockApi({ chatDelayMs: () => 0 });
    await expect(
      collect(api.sendChatMessage("nope", "hi")),
    ).rejects.toMatchObject({ status: 404, code: "chat_not_found" });
    const chat = await api.createChat();
    const first = api
      .sendChatMessage(chat.chat_id, "one")
      [Symbol.asyncIterator]();
    await first.next();
    await expect(
      collect(api.sendChatMessage(chat.chat_id, "two")),
    ).rejects.toMatchObject({ status: 409, code: "chat_busy" });
    await first.return?.();
  });

  it("gives each new chat its own ids", async () => {
    const api = createMockApi();
    const a = await api.createChat();
    const b = await api.createChat();
    expect(a.chat_id).not.toBe(b.chat_id);
    expect(a.session_id).not.toBe(b.session_id);
  });
});
