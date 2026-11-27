import { describe, expect, it } from "vitest";
import { createLiveApi, parseRunLog } from "./client";
import { createMockApi } from "./mock";
import { ApiError } from "./types";
import { runLogSummary } from "../components/display";

describe("createLiveApi.crawl", () => {
  it("POSTs the url to /crawl with the reviewer token and returns the JSON body", async () => {
    const calls: { url: string; init: RequestInit }[] = [];
    const fakeFetch = (async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      return new Response(JSON.stringify({ url: "https://example.com" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;

    const api = createLiveApi({
      baseUrl: "",
      getToken: () => "tok-123",
      fetch: fakeFetch,
    });
    const result = await api.crawl({ url: "https://example.com" });

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("/crawl");
    expect(calls[0].init.method).toBe("POST");
    expect(new Headers(calls[0].init.headers).get("X-Reviewer-Token")).toBe(
      "tok-123",
    );
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      url: "https://example.com",
    });
    expect(result).toEqual({ url: "https://example.com" });
  });

  it("maps a 401 to ApiError with the server code", async () => {
    const fakeFetch = (async () =>
      new Response(
        JSON.stringify({
          detail: "Missing or invalid X-Reviewer-Token",
          code: "unauthorized",
        }),
        {
          status: 401,
        },
      )) as typeof fetch;

    const api = createLiveApi({
      baseUrl: "",
      getToken: () => null,
      fetch: fakeFetch,
    });

    await expect(
      api.crawl({ url: "https://example.com" }),
    ).rejects.toMatchObject({
      status: 401,
      code: "unauthorized",
    });
  });

  it("exposes run_id from a 502 error body", async () => {
    const runId = "11111111-1111-4111-8111-111111111111";
    const fakeFetch = (async () =>
      new Response(
        JSON.stringify({
          detail: "fetch failed",
          code: "fetch_failed",
          run_id: runId,
        }),
        { status: 502 },
      )) as typeof fetch;
    const api = createLiveApi({
      baseUrl: "",
      getToken: () => null,
      fetch: fakeFetch,
    });
    await expect(
      api.crawl({ url: "https://example.com" }),
    ).rejects.toMatchObject({ status: 502, code: "fetch_failed", runId });
  });
});

const NDJSON = [
  '{"type":"run_start","run_id":"r1","kind":"crawl","session_id":null,"started_at":"2026-11-27T12:00:00Z","limits":{"memory_mb":512,"cpus":1,"timeout_s":30},"image_id":"sha256:x"}',
  '{"type":"msg","seq":1,"t_ms":3,"dir":"host_to_agent","msg":{"type":"task","url":"https://example.com"}}',
  '{"type":"msg","seq":2,"t_ms":9,"dir":"agent_to_host","raw":"not json"}',
  '{"type":"host","seq":3,"t_ms":690,"event":"fetch","status":200,"bytes":1256}',
  '{"type":"run_end","status":"ok","http_status":200,"error_code":null,"exit_code":0,"container_id":"c","elapsed_ms":2100,"stderr":"","stderr_truncated":false,"lines_dropped":0}',
].join("\n");

describe("parseRunLog", () => {
  it("returns one object per non-empty line, in order", () => {
    const lines = parseRunLog(`${NDJSON}\n\n`);
    expect(lines.map((l) => l.type)).toEqual([
      "run_start",
      "msg",
      "msg",
      "host",
      "run_end",
    ]);
  });

  it("accepts CRLF line endings", () => {
    expect(parseRunLog(NDJSON.replaceAll("\n", "\r\n"))).toHaveLength(5);
  });

  it("rejects a line that is not JSON", () => {
    expect(() => parseRunLog('{"type":"run_end"\nnope')).toThrow(/line 1/);
  });

  it("rejects an unknown line type or a msg without seq", () => {
    expect(() => parseRunLog('{"type":"other"}')).toThrow(/known line type/);
    expect(() =>
      parseRunLog('{"type":"msg","t_ms":1,"dir":"host_to_agent","msg":{}}'),
    ).toThrow(/known line type/);
  });
});

describe("createLiveApi.getCrawlRunLog", () => {
  it("GETs the NDJSON with the reviewer token and parses it", async () => {
    const calls: { url: string; init: RequestInit }[] = [];
    const fakeFetch = (async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      return new Response(NDJSON, {
        status: 200,
        headers: { "Content-Type": "application/x-ndjson" },
      });
    }) as typeof fetch;
    const api = createLiveApi({
      baseUrl: "http://h/",
      getToken: () => "tok-123",
      fetch: fakeFetch,
    });
    const lines = await api.getCrawlRunLog("r1");
    const headers = new Headers(calls[0].init.headers);
    expect(calls[0].url).toBe("http://h/crawl/runs/r1/log");
    expect(headers.get("X-Reviewer-Token")).toBe("tok-123");
    expect(headers.get("Accept")).toBe("application/x-ndjson");
    expect(lines).toHaveLength(5);
  });

  it("maps a 404 to ApiError not_found", async () => {
    const fakeFetch = (async () =>
      new Response(JSON.stringify({ detail: "x", code: "not_found" }), {
        status: 404,
      })) as typeof fetch;
    const api = createLiveApi({
      baseUrl: "",
      getToken: () => null,
      fetch: fakeFetch,
    });
    await expect(api.getCrawlRunLog("r1")).rejects.toMatchObject({
      status: 404,
      code: "not_found",
    });
  });
});

describe("mock run logs", () => {
  it("returns a success transcript for the crawl run_id", async () => {
    const api = createMockApi();
    const res = await api.crawl({ url: "https://example.com" });
    const lines = await api.getCrawlRunLog(res.run_id);
    expect(lines[0]).toMatchObject({ type: "run_start", run_id: res.run_id });
    expect(lines.at(-1)).toMatchObject({ type: "run_end", status: "ok" });
  });

  it("fails a .invalid host with run_id and an error transcript", async () => {
    const api = createMockApi();
    const err: unknown = await api
      .crawl({ url: "https://nowhere.invalid" })
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    const runId = (err as ApiError).runId;
    expect(runId).toBeTruthy();
    const lines = await api.getCrawlRunLog(runId ?? "");
    expect(lines.at(-1)).toMatchObject({
      type: "run_end",
      status: "error",
      error_code: "fetch_failed",
    });
  });
});

describe("runLogSummary", () => {
  it("summarises each line type", () => {
    const [start, task, raw, host, end] = parseRunLog(NDJSON);
    expect(runLogSummary(start)).toBe("crawl run, 512 MB, 1 CPU, 30 s");
    expect(runLogSummary(task)).toBe("task, url https://example.com");
    expect(runLogSummary(raw)).toBe("unparseable: not json");
    expect(runLogSummary(host)).toBe("fetch, status 200, bytes 1256");
    expect(runLogSummary(end)).toBe("ok, HTTP 200, exit 0, 2100 ms");
  });
});
