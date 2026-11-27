<script lang="ts">
  import {
    ApiError,
    getApi,
    getReviewerToken,
    setReviewerToken,
    type CrawlResult,
  } from "#lib/api/index.js";
  import Badge from "#lib/components/Badge.svelte";

  let url = $state("https://example.com");
  let token = $state(getReviewerToken() ?? "");
  let busy = $state(false);
  let error = $state<string | null>(null);
  let result = $state<CrawlResult | null>(null);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = null;
    result = null;
    setReviewerToken(token.trim() || null);
    try {
      result = await getApi().crawl({ url: url.trim() });
    } catch (err) {
      error =
        err instanceof ApiError
          ? `${err.message}${err.code ? ` (${err.code})` : ""}`
          : "The crawl failed. Try again.";
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head>
  <title>Crawl a page · Memory Quarantine</title>
</svelte:head>

<h1 class="font-title text-2xl font-semibold">Crawl a page</h1>
<p class="mt-2xs text-muted-foreground">
  One crawler agent runs in a disposable container with no network. The host fetches the page and
  asks the model to summarise it.
</p>

<form class="mt-lg grid gap-md rounded-lg border border-border bg-card p-lg" onsubmit={submit}>
  <div class="grid gap-2xs">
    <label class="text-sm font-medium" for="crawl-url">Page URL</label>
    <input
      id="crawl-url"
      name="url"
      type="url"
      required
      minlength="8"
      maxlength="2048"
      bind:value={url}
      class="h-control rounded-md border border-input bg-background px-md focus-visible:ring-2 focus-visible:ring-ring"
    />
  </div>
  <div class="grid gap-2xs">
    <label class="text-sm font-medium" for="crawl-token">Reviewer token</label>
    <input
      id="crawl-token"
      name="token"
      type="password"
      autocomplete="off"
      bind:value={token}
      class="h-control rounded-md border border-input bg-background px-md focus-visible:ring-2 focus-visible:ring-ring"
    />
    <p class="text-sm text-muted-foreground">Kept for this browser tab only (session storage).</p>
  </div>
  <div>
    <button
      type="submit"
      disabled={busy}
      class="h-control rounded-md bg-primary px-md text-primary-foreground disabled:bg-muted disabled:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
    >
      {busy ? "Crawling…" : "Crawl"}
    </button>
  </div>
</form>

<div aria-live="polite" class="mt-lg grid gap-md">
  {#if error}
    <p role="alert" class="rounded-lg border border-destructive p-md text-destructive">{error}</p>
  {/if}

  {#if result}
    <section aria-labelledby="crawl-result-title" class="grid gap-md rounded-lg border border-border bg-card p-lg">
      <div class="grid gap-2xs">
        <h2 id="crawl-result-title" class="font-title text-xl font-semibold">{result.title}</h2>
        <a class="break-all text-sm text-primary" href={result.final_url} rel="noreferrer">{result.final_url}</a>
      </div>
      <p class="rounded-md bg-muted p-sm break-words">{result.summary}</p>
      <ul class="grid list-disc gap-2xs pl-lg">
        {#each result.key_points as point (point)}
          <li>{point}</li>
        {/each}
      </ul>

      <dl class="grid gap-sm text-sm sm:grid-cols-[max-content_1fr]">
        <dt class="text-muted-foreground">Sandbox</dt>
        <dd>
          <Badge tone="success">Container removed</Badge>
          <Badge tone="outline">network {result.sandbox.network}</Badge>
        </dd>
        <dt class="text-muted-foreground">Container</dt>
        <dd class="font-mono break-all">{result.sandbox.container_id}</dd>
        <dt class="text-muted-foreground">Image</dt>
        <dd class="font-mono break-all">{result.sandbox.image_id}</dd>
        <dt class="text-muted-foreground">Limits</dt>
        <dd>
          {result.sandbox.limits.memory_mb} MB, {result.sandbox.limits.cpus} CPU,
          {result.sandbox.limits.timeout_s} s
        </dd>
        <dt class="text-muted-foreground">Model</dt>
        <dd>{result.model}</dd>
        <dt class="text-muted-foreground">Inference id</dt>
        <dd class="font-mono break-all">{result.inference_id}</dd>
        <dt class="text-muted-foreground">Elapsed</dt>
        <dd>{result.elapsed_ms} ms</dd>
      </dl>
    </section>
  {/if}
</div>
