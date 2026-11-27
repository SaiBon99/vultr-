const env = import.meta.env;
import { createLiveApi } from "./client";
import { createMockApi } from "./mock";
import type { ApiMode, ReviewApi } from "./types";

export * from "./types";

const TOKEN_KEY = "reviewer_token";

/** Reviewer token: session storage (set after sign-in) or PUBLIC_REVIEWER_TOKEN for local dev. */
export function getReviewerToken(): string | null {
  if (typeof sessionStorage !== "undefined") {
    const stored = sessionStorage.getItem(TOKEN_KEY);
    if (stored) return stored;
  }
  return env.PUBLIC_REVIEWER_TOKEN || null;
}

export function setReviewerToken(token: string | null): void {
  if (token) sessionStorage.setItem(TOKEN_KEY, token);
  else sessionStorage.removeItem(TOKEN_KEY);
}

export function apiMode(): ApiMode {
  return env.PUBLIC_API_MODE === "live" ? "live" : "mock";
}

let instance: ReviewApi | undefined;

export function getApi(): ReviewApi {
  instance ??=
    apiMode() === "live"
      ? createLiveApi({
          baseUrl: import.meta.env.PUBLIC_API_BASE || "http://localhost:8000",
          getToken: getReviewerToken,
        })
      : createMockApi();
  return instance;
}
