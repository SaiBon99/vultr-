<script lang="ts">
  import FileText from "@lucide/svelte/icons/file-text";
  import Mail from "@lucide/svelte/icons/mail";
  import {
    getApi,
    type DecideResponse,
    type QuarantineItem,
    type QuarantineSessionGroup,
    type Receipt,
  } from "#lib/api/index.js";
  import { formatTime, shortHash } from "#lib/format.js";
  import Badge from "./Badge.svelte";
  import DecisionPanel from "./DecisionPanel.svelte";
  import JudgePanel from "./JudgePanel.svelte";
  import ReceiptPanel from "./ReceiptPanel.svelte";
  import RiskMeter from "./RiskMeter.svelte";
  import RuleFlags from "./RuleFlags.svelte";
  import VerdictBadge from "./VerdictBadge.svelte";
  import { statusLabel, statusTone } from "./display.js";

  let {
    item,
    session,
    receipt = null,
    ondecided,
    onstale,
  }: {
    item: QuarantineItem;
    session: QuarantineSessionGroup | undefined;
    receipt?: Receipt | null;
    ondecided: (res: DecideResponse) => void;
    onstale?: () => void;
  } = $props();

  let fetched = $state<Receipt | null>(null);
  let receiptError = $state<string | null>(null);

  $effect(() => {
    const id = item.receipt_id;
    fetched = null;
    receiptError = null;
    if (!id || receipt) return;
    getApi()
      .getReceipt(id)
      .then((r) => {
        if (item.receipt_id === id) fetched = r;
      })
      .catch(() => (receiptError = "Could not load the receipt for this row."));
  });

  const shown = $derived(receipt ?? fetched);
  const SourceIcon = $derived(item.source_ref?.startsWith("email:") ? Mail : FileText);
</script>

<article aria-labelledby="inspector-title" class="grid gap-lg rounded-lg border border-border bg-card p-lg" data-testid="inspector">
  <header class="grid gap-xs">
    <div class="flex flex-wrap items-center gap-xs">
      <VerdictBadge verdict={item.verdict} />
      <Badge tone={statusTone[item.status]}>{statusLabel[item.status]}</Badge>
    </div>
    <h2 id="inspector-title" class="font-title text-xl font-semibold text-balance">
      {session?.label ?? "Unlabelled session"}, write at {formatTime(item.created_at)}
    </h2>
  </header>

  <RiskMeter {item} />

  <div class="grid gap-md md:grid-cols-2">
    <section aria-labelledby="source-title" class="grid content-start gap-xs">
      <h3 id="source-title" class="text-sm font-medium text-muted-foreground">What the agent read</h3>
      {#if item.source_snippet}
        <blockquote class="rounded-md bg-muted p-sm text-sm text-pretty break-words">{item.source_snippet}</blockquote>
        <p class="flex items-center gap-xs text-sm text-muted-foreground">
          <SourceIcon class="size-4" aria-hidden="true" />
          <span class="font-mono break-all">{item.source_ref}</span>
        </p>
      {:else}
        <p class="rounded-md border border-dashed border-border p-sm text-sm text-muted-foreground">
          No external read tied to this write. Source: {item.source}.
        </p>
      {/if}
    </section>
    <section aria-labelledby="proposed-title" class="grid content-start gap-xs">
      <h3 id="proposed-title" class="text-sm font-medium text-muted-foreground">Proposed memory</h3>
      {#if item.content !== null}
        <p class="rounded-md border border-border bg-background p-sm text-sm text-pretty break-words">{item.content}</p>
      {:else}
        <p class="rounded-md border border-dashed border-border p-sm text-sm text-muted-foreground">
          Content purged. The hash stays for the audit trail.
        </p>
      {/if}
      <p class="text-sm text-muted-foreground">Hash <span class="font-mono">{shortHash(item.payload_hash)}</span></p>
    </section>
  </div>

  <RuleFlags flags={item.rule_flags} />
  <JudgePanel {item} />

  {#if item.status === "quarantined"}
    {#key item.id}
      <DecisionPanel {item} {ondecided} {onstale} />
    {/key}
  {:else}
    <p class="text-sm text-muted-foreground">
      {statusLabel[item.status]} by {item.decided_by ?? "reviewer"}{item.decided_at ? ` at ${formatTime(item.decided_at)}` : ""}.
      {#if item.override_reason}Reason: {item.override_reason}{/if}
    </p>
  {/if}

  {#if shown}
    <ReceiptPanel receipt={shown} />
  {:else if receiptError}
    <p class="text-sm text-destructive" role="alert">{receiptError}</p>
  {/if}
</article>
