<script lang="ts">
  import ShieldCheck from "@lucide/svelte/icons/shield-check";
  import ShieldX from "@lucide/svelte/icons/shield-x";
  import Badge from "#lib/components/Badge.svelte";
  import { formatTime, shortHash } from "#lib/format.js";
  import type { PageProps } from "./$types";

  let { data }: PageProps = $props();
  const valid = $derived(data.log.chain_valid && data.local.valid);
</script>

<h1 class="font-title text-2xl font-semibold">Audit log</h1>

<section
  aria-label="Chain status"
  class="mt-md flex items-start gap-sm rounded-lg border border-border bg-card p-md"
  data-testid="chain-status"
>
  {#if valid}
    <ShieldCheck class="mt-2xs size-5 text-success" aria-hidden="true" />
  {:else}
    <ShieldX class="mt-2xs size-5 text-destructive" aria-hidden="true" />
  {/if}
  <div>
    <p class="font-title font-semibold">chain_valid: {valid ? "true" : "false"}</p>
    <p class="text-sm text-muted-foreground">
      {#if valid}
        {data.log.events.length} events verified in this browser. Head {shortHash(data.log.head_hash)}.
      {:else}
        First invalid event: seq {data.log.first_invalid_seq ?? data.local.first_invalid_seq}.
      {/if}
    </p>
  </div>
</section>

<div class="mt-lg overflow-x-auto rounded-lg border border-border bg-card">
  <table class="w-full text-left text-sm">
    <caption class="sr-only">Hash-chained audit events</caption>
    <thead class="border-b border-border text-muted-foreground">
      <tr>
        <th scope="col" class="p-sm font-medium">Seq</th>
        <th scope="col" class="p-sm font-medium">Event</th>
        <th scope="col" class="p-sm font-medium">Time</th>
        <th scope="col" class="p-sm font-medium">Hash</th>
      </tr>
    </thead>
    <tbody class="divide-y divide-border">
      {#each data.log.events as event (event.seq)}
        <tr>
          <td class="p-sm tabular-nums">{event.seq}</td>
          <td class="p-sm"><Badge tone="neutral">{event.event_type.replaceAll("_", " ")}</Badge></td>
          <td class="p-sm whitespace-nowrap">{formatTime(event.created_at)}</td>
          <td class="p-sm font-mono">{shortHash(event.event_hash)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
