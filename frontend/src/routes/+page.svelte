<script lang="ts">
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import { tick } from "svelte";
  import { page } from "$app/state";
  import {
    ApiError,
    describeError,
    getApi,
    getReviewerToken,
    setReviewerToken,
    type DecideResponse,
    type QuarantineItem,
    type QuarantineList,
    type QuarantineSessionGroup,
    type QuarantineStatus,
    type Receipt,
  } from "#lib/api/index.js";
  import Badge from "#lib/components/Badge.svelte";
  import Inspector from "#lib/components/Inspector.svelte";
  import VerdictBadge from "#lib/components/VerdictBadge.svelte";
  import { statusLabel, statusTone } from "#lib/components/display.js";
  import { formatTime } from "#lib/format.js";
  import { sortQueue } from "#lib/review.js";
  import type { PageProps } from "./$types";

  let { data }: PageProps = $props();

  let list = $derived<QuarantineList | null>(data.list ? sortQueue(data.list) : null);
  let error = $derived(data.error);
  let errorStatus = $derived(data.status);
  let filter = $state<QuarantineStatus | "all">("quarantined");
  /** ?item=<quarantine id> preselects a row, e.g. from a chat remember step. */
  let selectedId = $state<string | null>(page.url.searchParams.get("item"));
  let token = $state(getReviewerToken() ?? "");
  // Follow ?item= on same-route navigation (links from chat, Back); manual picks stand until the URL changes.
  let urlItem = $derived(page.url.searchParams.get("item"));
  $effect(() => {
    if (urlItem) selectedId = urlItem;
  });
  /** Rows decided in this tab, kept so the inspector can show the receipt after the row leaves the queue. */
  let decided = $state<
    Record<string, { item: QuarantineItem; receipt: Receipt; session: QuarantineSessionGroup | undefined }>
  >({});

  const sessions = $derived(list?.sessions ?? []);
  const rows = $derived(sessions.flatMap((s) => s.items));
  const selected = $derived(
    (selectedId ? (decided[selectedId]?.item ?? rows.find((i) => i.id === selectedId)) : undefined) ?? rows[0],
  );
  const selectedSession = $derived(
    sessions.find((s) => s.session_id === selected?.session_id) ?? (selected ? decided[selected.id]?.session : undefined),
  );
  const pending = $derived(rows.some((i) => i.judge_status === "pending"));
  const awaiting = $derived(rows.filter((i) => i.status === "quarantined").length);

  let requestSeq = 0;
  async function refresh() {
    const seq = ++requestSeq;
    try {
      const next = sortQueue(await getApi().listQuarantine(filter === "all" ? undefined : filter));
      if (seq !== requestSeq) return;
      list = next;
      error = null;
    } catch (err) {
      if (seq !== requestSeq) return;
      error = describeError(err, "Could not load the quarantine queue.");
      errorStatus = err instanceof ApiError ? err.status : 0;
    }
  }

  // Poll while the judge is still evaluating a visible row.
  $effect(() => {
    if (!pending) return;
    const timer = setInterval(refresh, 2500);
    return () => clearInterval(timer);
  });

  function setFilter(next: typeof filter) {
    filter = next;
    void refresh();
  }

  async function select(id: string) {
    selectedId = id;
    if (!matchMedia("(min-width: 64rem)").matches) {
      await tick();
      document.getElementById("inspector")?.scrollIntoView({ block: "start" });
    }
  }

  function ondecided(res: DecideResponse) {
    decided[res.item.id] = { item: res.item, receipt: res.receipt, session: selectedSession };
    selectedId = res.item.id;
    void refresh();
  }

  function saveToken(event: SubmitEvent) {
    event.preventDefault();
    setReviewerToken(token.trim() || null);
    void refresh();
  }

  const filters = [
    { value: "quarantined", label: "Awaiting decision" },
    { value: "all", label: "All rows" },
  ] as const;
</script>

<svelte:head>
  <title>Quarantine review · Memory Quarantine</title>
</svelte:head>

<div class="flex flex-wrap items-end justify-between gap-md">
  <div class="grid gap-2xs">
    <h1 class="font-title text-2xl font-semibold text-balance">Quarantine review</h1>
    <p class="text-pretty text-muted-foreground">
      Writes frozen by the gate, highest priority first. Purge or override each one; every decision is signed.
    </p>
  </div>
  <div class="flex gap-2xs rounded-lg bg-muted p-2xs" role="group" aria-label="Filter rows">
    {#each filters as f (f.value)}
      <button
        type="button"
        aria-pressed={filter === f.value}
        onclick={() => setFilter(f.value)}
        class="h-control rounded-md px-sm text-sm font-medium text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring aria-pressed:bg-card aria-pressed:text-foreground aria-pressed:shadow-sm"
      >
        {f.label}
      </button>
    {/each}
  </div>
</div>

{#if error}
  <div class="mt-lg grid gap-sm rounded-lg border border-destructive bg-card p-lg" role="alert">
    <p class="font-medium text-destructive">{error}</p>
    {#if errorStatus === 401}
      <form class="flex flex-wrap items-end gap-sm" onsubmit={saveToken}>
        <div class="grid gap-2xs">
          <label class="text-sm font-medium" for="review-token">Reviewer token</label>
          <input
            id="review-token"
            type="password"
            autocomplete="off"
            bind:value={token}
            class="h-control rounded-md border border-input bg-background px-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          />
        </div>
        <button type="submit" class="h-control rounded-md bg-primary px-md text-sm font-medium text-primary-foreground focus-visible:ring-2 focus-visible:ring-ring">
          Save and retry
        </button>
      </form>
    {:else}
      <button type="button" onclick={refresh} class="h-control justify-self-start rounded-md bg-secondary px-md text-sm font-medium text-secondary-foreground hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring">
        Retry
      </button>
    {/if}
  </div>
{:else if rows.length === 0 && !selected}
  <div class="mt-lg grid justify-items-start gap-sm rounded-lg border border-border bg-card p-lg">
    <p class="font-medium">Nothing is waiting for a decision.</p>
    <p class="text-sm text-muted-foreground">Every frozen write has been purged or overridden. Past decisions stay in the full list.</p>
    {#if filter !== "all"}
      <button type="button" onclick={() => setFilter("all")} class="h-control rounded-md bg-secondary px-md text-sm font-medium text-secondary-foreground hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring">
        Show all rows
      </button>
    {/if}
  </div>
{:else}
  <div class="mt-lg grid items-start gap-lg lg:grid-cols-5">
    <nav aria-label="Quarantine queue" class="grid gap-md lg:col-span-2">
      <p class="text-sm text-muted-foreground">
        {awaiting} awaiting decision across {sessions.length} {sessions.length === 1 ? "session" : "sessions"}
      </p>
      {#each sessions as session (session.session_id)}
        <section aria-labelledby="session-{session.session_id}" class="grid gap-xs">
          <div class="flex flex-wrap items-center justify-between gap-xs px-2xs">
            <h2 id="session-{session.session_id}" class="font-title text-base font-semibold">
              {session.label ?? "Unlabelled session"}
            </h2>
            <span class="flex items-center gap-xs">
              {#if session.tainted}<Badge tone="warning">Tainted</Badge>{/if}
              <span class="text-sm text-muted-foreground tabular-nums">{session.write_count} writes</span>
            </span>
          </div>
          <ul class="grid gap-2xs">
            {#each session.items as item (item.id)}
              <li data-testid="quarantine-row">
                <button
                  type="button"
                  aria-current={selected?.id === item.id ? "true" : undefined}
                  onclick={() => select(item.id)}
                  class="grid w-full gap-xs rounded-lg border border-border bg-card p-sm text-left hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring aria-[current=true]:border-ring aria-[current=true]:bg-accent"
                >
                  <span class="flex flex-wrap items-center gap-xs">
                    <VerdictBadge verdict={item.verdict} />
                    {#if item.status !== "quarantined"}
                      <Badge tone={statusTone[item.status]}>{statusLabel[item.status]}</Badge>
                    {/if}
                    {#if item.judge_status === "pending"}
                      <span class="flex items-center gap-2xs text-xs text-muted-foreground">
                        <LoaderCircle class="size-3.5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                        Evaluating
                      </span>
                    {/if}
                    <span class="ml-auto text-sm font-semibold tabular-nums">
                      <span class="sr-only">Risk </span>{item.risk_score}<span class="sr-only"> of 100</span>
                    </span>
                  </span>
                  <span class="line-clamp-2 text-sm">
                    {item.content ?? "Content purged."}
                  </span>
                  <span class="text-xs text-muted-foreground">{formatTime(item.created_at)}</span>
                </button>
              </li>
            {/each}
          </ul>
        </section>
      {/each}
    </nav>

    <div id="inspector" class="scroll-mt-md lg:sticky lg:top-md lg:col-span-3">
      {#if selected}
        <Inspector
          item={selected}
          session={selectedSession}
          receipt={decided[selected.id]?.receipt ?? null}
          {ondecided}
          onstale={refresh}
        />
      {/if}
    </div>
  </div>
{/if}
