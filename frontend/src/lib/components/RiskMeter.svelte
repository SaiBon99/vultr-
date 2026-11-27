<script lang="ts">
  import type { QuarantineItem } from "#lib/api/index.js";
  import { RULEBOOK, judgeBoost, weightSum } from "#lib/review.js";

  let { item }: { item: QuarantineItem } = $props();
  const boost = $derived(judgeBoost(item));
  const sum = $derived(weightSum(item.rule_flags));
  const fill = $derived(item.verdict === "NEEDS_REVIEW" ? "bg-warning" : "bg-destructive");
  const basis = $derived.by(() => {
    if (item.verdict === "FAIL_CLOSED" && item.risk_score === RULEBOOK.fail_closed_floor && sum < item.risk_score)
      return `Rule weights add to ${sum}; fail-closed rows start at ${RULEBOOK.fail_closed_floor}.`;
    if (sum > 100) return `Rule weights add to ${sum}, capped at 100.`;
    return `Sum of the failed rule weights.`;
  });
</script>

<div class="grid gap-xs">
  <div class="flex items-baseline justify-between gap-sm">
    <span class="text-sm font-medium text-muted-foreground" id="risk-{item.id}">Risk score</span>
    <span class="flex items-baseline gap-xs">
      <span class="font-title text-3xl font-semibold tabular-nums">{item.risk_score}</span>
      <span class="text-sm text-muted-foreground">/ 100</span>
    </span>
  </div>
  <div
    role="meter"
    aria-labelledby="risk-{item.id}"
    aria-valuemin={0}
    aria-valuemax={100}
    aria-valuenow={item.risk_score}
    class="h-2 overflow-hidden rounded-full bg-muted"
  >
    <div class="h-full rounded-full {fill}" style:width="{item.risk_score}%"></div>
  </div>
  <p class="text-sm text-muted-foreground">{basis}</p>
  {#if boost > 0}
    <p class="text-sm" data-testid="judge-boost">
      <span class="font-medium">Queue priority {item.effective_priority_score}:</span>
      <span class="text-muted-foreground"
        >risk {item.risk_score} plus {boost} because the judge recommends purge at
        {item.judge_note?.risk_level ?? "high"} risk.</span
      >
    </p>
  {/if}
</div>
