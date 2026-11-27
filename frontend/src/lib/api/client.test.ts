import { describe, expect, it } from "vitest";
import { createLiveApi } from "./client";

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
});
