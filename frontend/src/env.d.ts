/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly PUBLIC_API_MODE?: "mock" | "live";
  readonly PUBLIC_API_BASE?: string;
  readonly PUBLIC_REVIEWER_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
