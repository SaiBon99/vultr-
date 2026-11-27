<script lang="ts">
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import Scale from "@lucide/svelte/icons/scale";
  import TriangleAlert from "@lucide/svelte/icons/triangle-alert";
  import type { QuarantineItem } from "#lib/api/index.js";
  import { RULEBOOK, judgeFailure } from "#lib/review.js";
  import Badge from "./Badge.svelte";

  let { item }: { item: QuarantineItem } = $props();
  const failure = $derived(judgeFailure(item));
  const riskTone = { low: "neutral", medium: "warning", high: "danger", critical: "danger" } as const;
</script>

<section aria-labelledby="judge-title" aria-live="polite" class="grid gap-sm rounded-lg border border-border p-md">
  <h3 id="judge-title" class="flex items-center gap-xs font-title text-base font-semibold">
    <Scale class="size-4 text-muted-foreground" aria-hidden="true" />
    Isolated judge
  </h3>

  {#if item.judge_status === "pending"}
    <p class="flex items-center gap-xs text-sm" data-testid="judge-evaluating">
      <LoaderCircle class="size-4 animate-spin text-muted-foreground motion-reduce:animate-none" aria-hidden="true" />
      <span class="font-medium">Evaluating</span>
      <span class="text-muted-foreground">The verdict already stands on the rules; the judge only explains.</span>
    </p>
  {:else if item.judge_status === "failed"}
    <div class="flex items-start gap-xs text-sm" role="note" data-testid="judge-failed">
      <TriangleAlert class="mt-2xs size-4 shrink-0 text-destructive" aria-hidden="true" />
      <div class="grid gap-2xs">
        <p class="font-medium">Judge failed (timeout or invalid output).</p>
        {#if failure === "escalated"}
          <p class="text-pretty text-muted-foreground">
            Escalated from Needs review to Fail closed, with the risk score raised to at least
            {RULEBOOK.fail_closed_floor}. A failed judge never lets a write through.
          </p>
        {:else}
          <p class="text-pretty text-muted-foreground">The verdict and risk score are unchanged.</p>
        {/if}
      </div>
    </div>
  {:else if item.judge_note}
    {@const note = item.judge_note}
    <div class="flex flex-wrap items-center gap-xs">
      <Badge tone={riskTone[note.risk_level]}>{note.risk_level} risk</Badge>
      <Badge tone="outline">Suggests {note.recommended_action}</Badge>
    </div>
    <p class="text-sm text-pretty">{note.summary}</p>
    {#if note.indicators.length}
      <ul class="flex flex-wrap gap-xs" aria-label="Indicators">
        {#each note.indicators as indicator (indicator)}
          <li><Badge tone="neutral">{indicator}</Badge></li>
        {/each}
      </ul>
    {/if}
  {:else}
    <p class="text-sm text-muted-foreground">No judge note. The verdict stands on the rules alone.</p>
  {/if}
</section>
