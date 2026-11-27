import { ApiError, type ReviewApi } from "./types";

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

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (init.body) headers.set("Content-Type", "application/json");
    const token = getToken();
    if (token) headers.set("X-Reviewer-Token", token);
    const res = await f(`${root}${path}`, { ...init, headers });
    if (!res.ok) {
      const err = (await res.json().catch(() => null)) as {
        detail?: string;
        code?: string;
      } | null;
      throw new ApiError(res.status, err?.detail ?? res.statusText, err?.code);
    }
    return (await res.json()) as T;
  }

  const qs = (params: Record<string, string | undefined>) => {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) p.set(k, v);
    const s = p.toString();
    return s ? `?${s}` : "";
  };

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
  };
}
