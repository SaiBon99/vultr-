<script lang="ts">
  import { Accordion } from "@ark-ui/svelte/accordion";
  import ChevronDown from "@lucide/svelte/icons/chevron-down";
  import Badge from "#lib/components/Badge.svelte";
  import { flagLabel, statusTone, verdictLabel, verdictTone } from "#lib/components/display.js";
  import { formatTime, shortHash } from "#lib/format.js";
  import type { PageProps } from "./$types";

  let { data }: PageProps = $props();
  const sessions = $derived(data.list.sessions);
</script>

<h1 class="font-title text-2xl font-semibold">Quarantine</h1>
<p class="mt-2xs text-muted-foreground">Writes frozen by the gate, grouped by session, newest first.</p>

{#if sessions.length === 0}
  <p class="mt-lg rounded-lg border border-border bg-card p-lg text-muted-foreground">
    No quarantined writes.
  </p>
{:else}
  <Accordion.Root multiple defaultValue={sessions.map((s) => s.session_id)} class="mt-lg grid gap-md">
    {#each sessions as session (session.session_id)}
      <Accordion.Item value={session.session_id} class="rounded-lg border border-border bg-card">
        <Accordion.ItemTrigger
          class="flex w-full items-center justify-between gap-md rounded-lg p-md text-left hover:bg-accent"
        >
          <span class="grid gap-2xs">
            <span class="font-title font-semibold">{session.label ?? "Unlabelled session"}</span>
            <span class="text-sm text-muted-foreground">
              {session.write_count} writes, {session.items.length} frozen,
              {session.external_sources.length} external reads, started {formatTime(session.created_at)}
            </span>
          </span>
          <span class="flex items-center gap-xs">
            {#if session.tainted}<Badge tone="warning">Tainted</Badge>{/if}
            <Accordion.ItemIndicator class="transition-transform data-[state=open]:rotate-180">
              <ChevronDown class="size-4" aria-hidden="true" />
            </Accordion.ItemIndicator>
          </span>
        </Accordion.ItemTrigger>
        <Accordion.ItemContent>
          <ul class="grid divide-y divide-border border-t border-border">
            {#each session.items as item (item.id)}
              <li class="grid gap-sm p-md" data-testid="quarantine-row">
                <div class="flex flex-wrap items-center gap-xs">
                  <Badge tone={verdictTone[item.verdict]}>{verdictLabel[item.verdict]}</Badge>
                  {#each item.rule_flags as flag (flag)}
                    <Badge tone="neutral">{flagLabel(flag)}</Badge>
                  {/each}
                  <span class="ml-auto"><Badge tone={statusTone[item.status]}>{item.status}</Badge></span>
                </div>
                <p class="rounded-md bg-muted p-sm text-sm break-words">
                  {item.content ?? "Content purged. Hash kept for the audit trail."}
                </p>
                <p class="text-sm text-muted-foreground">
                  Hash <span class="font-mono">{shortHash(item.payload_hash)}</span>
                  {#if item.source_ref}, from <span class="font-mono">{item.source_ref}</span>{/if}
                </p>
                {#if item.judge_note}
                  <div class="grid gap-2xs rounded-md border border-border p-sm text-sm">
                    <p>
                      <span class="font-medium"
                        >Judge: {item.judge_note.risk_level} risk, suggests {item.judge_note.recommended_action}.</span
                      >
                      {item.judge_note.summary}
                    </p>
                    {#if item.judge_note.indicators.length}
                      <ul class="flex flex-wrap gap-xs">
                        {#each item.judge_note.indicators as indicator (indicator)}
                          <li><Badge tone="outline">{indicator}</Badge></li>
                        {/each}
                      </ul>
                    {/if}
                  </div>
                {:else}
                  <p class="text-sm text-muted-foreground">
                    No judge note ({item.judge_status}). The verdict stands on rule flags alone.
                  </p>
                {/if}
              </li>
            {/each}
          </ul>
        </Accordion.ItemContent>
      </Accordion.Item>
    {/each}
  </Accordion.Root>
{/if}
