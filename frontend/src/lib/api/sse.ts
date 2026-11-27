/**
 * Minimal Server-Sent Events parser for POST streams (EventSource cannot POST).
 * Yields the joined `data:` payload of each event; ignores comments and the
 * event, id and retry fields, which the chat stream does not use.
 */
export interface SseParser {
  /** Feeds decoded text; returns the payloads of events completed by it. */
  push(chunk: string): string[];
  /** Flushes a final event that had no trailing blank line. */
  end(): string[];
}

export function createSseParser(): SseParser {
  let buffer = "";
  let data: string[] = [];

  function dispatch(out: string[]) {
    if (data.length) out.push(data.join("\n"));
    data = [];
  }

  function line(text: string, out: string[]) {
    if (text === "") return dispatch(out);
    if (text.startsWith(":")) return;
    const colon = text.indexOf(":");
    const field = colon === -1 ? text : text.slice(0, colon);
    let value = colon === -1 ? "" : text.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "data") data.push(value);
  }

  return {
    push(chunk) {
      buffer += chunk;
      const out: string[] = [];
      for (;;) {
        const i = buffer.search(/[\r\n]/);
        if (i === -1) break;
        // A trailing \r may be the first half of \r\n; wait for the next chunk.
        if (buffer[i] === "\r" && i === buffer.length - 1) break;
        const width = buffer[i] === "\r" && buffer[i + 1] === "\n" ? 2 : 1;
        line(buffer.slice(0, i), out);
        buffer = buffer.slice(i + width);
      }
      return out;
    },
    end() {
      const out: string[] = [];
      if (buffer) line(buffer.replace(/\r$/, ""), out);
      buffer = "";
      dispatch(out);
      return out;
    },
  };
}

/** Reads a byte stream as SSE and yields each event's data payload. */
export async function* readSse(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<string> {
  const parser = createSseParser();
  const decoder = new TextDecoder();
  const reader = body.getReader();
  let finished = false;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      yield* parser.push(decoder.decode(value, { stream: true }));
    }
    finished = true;
    yield* parser.push(decoder.decode());
    yield* parser.end();
  } finally {
    // The consumer stopped early: close the connection instead of leaving it open.
    if (!finished) await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
