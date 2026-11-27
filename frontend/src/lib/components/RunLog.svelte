<script lang="ts">
  import { ApiError, getApi, type RunLogLine } from "#lib/api/index.js";
  import Badge from "#lib/components/Badge.svelte";
  import { runLogSummary } from "#lib/components/display.js";

  /** Which run family the id belongs to; chat runs live under /chat/runs. */
  let { runId, source = "crawl" }: { runId: string; source?: "crawl" | "chat" } = $props();

  let lines = $state<RunLogLine[] | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(false);

  /** Loads the transcript the first time the reviewer opens the list. */
  async function load(event: Event) {
    if (!(event.currentTarget as HTMLDetailsElement).open || lines || loading) return;
    loading = true;
    error = null;
    try {
      const api = getApi();
      lines = await (source === "chat" ? api.getChatRunLog(runId) : api.getCrawlRunLog(runId));
    } catch (err) {
      error =
        err instanceof ApiError
          ? `${err.message}${err.code ? ` (${err.code})` : ""}`
          : "The run log could not be read.";
    } finally {
      loading = false;
    }
  }

  const seq = (line: RunLogLine): string =>
    line.type === "msg" || line.type === "host" ? String(line.seq) : "";
  const tMs = (line: RunLogLine): string =>
    line.type === "msg" || line.type === "host" ? `${line.t_ms} ms` : "";
  const dir = (line: RunLogLine): string =>
    line.type === "msg" ? (line.dir === "host_to_agent" ? "host → agent" : "agent → host") : "";
</script>

<details class="rounded-lg border border-border bg-card" ontoggle={load} data-testid="run-log">
  <summary class="cursor-pointer p-md font-medium focus-visible:ring-2 focus-visible:ring-ring">Run log</summary>
  <div class="grid gap-sm border-t border-border p-md" aria-live="polite">
    {#if loading}
      <p class="text-sm text-muted-foreground">Loading run log…</p>
    {:else if error}
      <p role="alert" class="text-sm text-destructive">{error}</p>
    {:else if lines}
      <div class="overflow-x-auto">
        <table class="w-full text-left text-sm">
          <caption class="sr-only">Run log lines for run {runId}</caption>
          <thead class="border-b border-border text-muted-foreground">
            <tr>
              <th scope="col" class="p-xs font-medium">Seq</th>
              <th scope="col" class="p-xs font-medium">Type</th>
              <th scope="col" class="p-xs font-medium">Direction</th>
              <th scope="col" class="p-xs font-medium">Time</th>
              <th scope="col" class="p-xs font-medium">Summary</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border">
            {#each lines as line, i (i)}
              <tr data-testid="run-log-line" class="align-top">
                <td class="p-xs tabular-nums">{seq(line)}</td>
                <td class="p-xs"><Badge tone="neutral">{line.type.replaceAll("_", " ")}</Badge></td>
                <td class="p-xs whitespace-nowrap">{dir(line)}</td>
                <td class="p-xs whitespace-nowrap tabular-nums">{tMs(line)}</td>
                <td class="p-xs">
                  <details>
                    <summary class="cursor-pointer break-words focus-visible:ring-2 focus-visible:ring-ring">
                      {runLogSummary(line)}
                    </summary>
                    <pre
                      class="mt-2xs overflow-auto rounded-md bg-muted p-sm font-mono text-xs whitespace-pre-wrap break-all">{JSON.stringify(
                        line,
                        null,
                        2,
                      )}</pre>
                  </details>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </div>
</details>
