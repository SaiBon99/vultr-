import { describe, expect, it } from "vitest";
import { createSseParser, readSse } from "./sse";

const feed = (chunks: string[]) => {
  const p = createSseParser();
  return [...chunks.flatMap((c) => p.push(c)), ...p.end()];
};

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(enc.encode(c));
      controller.close();
    },
  });
}

describe("SSE parser", () => {
  it("reassembles an event split mid-line across chunks", () => {
    expect(feed(['data: {"ty', 'pe":"run"}\n', "\n"])).toEqual([
      '{"type":"run"}',
    ]);
  });

  it("emits several events from one chunk", () => {
    expect(feed(["data: a\n\ndata: b\n\ndata: c\n\n"])).toEqual([
      "a",
      "b",
      "c",
    ]);
  });

  it("flushes a final event without a trailing blank line", () => {
    expect(feed(["data: a\n\n", "data: last"])).toEqual(["a", "last"]);
    expect(feed(["data: last\n"])).toEqual(["last"]);
  });

  it("handles CRLF split between chunks, comments, other fields and multi-line data", () => {
    expect(
      feed([
        ": keep-alive\r",
        "\nevent: step\r\nid: 1\r\ndata: one\r\ndata:two\r",
        "\n\r\n",
      ]),
    ).toEqual(["one\ntwo"]);
  });

  it("ignores blank lines with no data", () => {
    expect(feed(["\n\n: ping\n\n"])).toEqual([]);
  });

  it("decodes a byte stream with a multi-byte character split across chunks", async () => {
    const bytes = new TextEncoder().encode('data: {"t":"é"}\n\n');
    const split = bytes.indexOf(0xc3) + 1;
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(bytes.slice(0, split));
        c.enqueue(bytes.slice(split));
        c.close();
      },
    });
    const out: string[] = [];
    for await (const d of readSse(stream)) out.push(d);
    expect(out).toEqual(['{"t":"é"}']);
  });

  it("reads every event from a byte stream", async () => {
    const out: string[] = [];
    for await (const d of readSse(
      streamOf(["data: 1\n\nda", "ta: 2\n\ndata: 3"]),
    ))
      out.push(d);
    expect(out).toEqual(["1", "2", "3"]);
  });
});
