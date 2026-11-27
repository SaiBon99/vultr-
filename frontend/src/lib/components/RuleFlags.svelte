<script lang="ts">
  import { Collapsible } from "@ark-ui/svelte/collapsible";
  import Check from "@lucide/svelte/icons/check";
  import ChevronDown from "@lucide/svelte/icons/chevron-down";
  import CircleX from "@lucide/svelte/icons/circle-x";
  import type { RuleFlag } from "#lib/api/index.js";
  import { ALL_FLAGS, RULES, splitFlags } from "#lib/review.js";
  import { verdictLabel } from "./display.js";

  let { flags }: { flags: RuleFlag[] } = $props();
  const split = $derived(splitFlags(flags));
</script>

<section aria-labelledby="rules-title" class="grid gap-sm">
  <h3 id="rules-title" class="font-title text-base font-semibold">
    Gate rules
    <span class="font-content text-sm font-normal text-muted-foreground"
      >{split.failed.length} failed, {split.passed.length}/{ALL_FLAGS.length} passed</span
    >
  </h3>

  <ul class="grid gap-xs" data-testid="failed-rules">
    {#each split.failed as flag (flag)}
      {@const rule = RULES[flag]}
      <li class="flex items-start gap-sm rounded-md bg-muted p-sm">
        <CircleX class="mt-2xs size-4 shrink-0 text-destructive" aria-hidden="true" />
        <div class="grid flex-1 gap-2xs">
          <p class="text-sm font-medium">
            {rule.label}<span class="font-normal text-muted-foreground"
              >, {verdictLabel[rule.verdict].toLowerCase()} tier</span
            >
          </p>
          <p class="text-sm text-pretty text-muted-foreground">{rule.reason}</p>
        </div>
        <span class="text-sm font-medium tabular-nums" aria-label="weight {rule.weight}">
          {rule.weight > 0 ? `+${rule.weight}` : "floor"}
        </span>
      </li>
    {/each}
  </ul>

  <Collapsible.Root>
    <Collapsible.Trigger
      class="flex h-control w-full items-center justify-between gap-sm rounded-md px-sm text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span class="flex items-center gap-xs">
        <Check class="size-4 text-success" aria-hidden="true" />
        {split.passed.length}/{ALL_FLAGS.length} passed
      </span>
      <Collapsible.Indicator class="transition-transform data-[state=open]:rotate-180">
        <ChevronDown class="size-4" aria-hidden="true" />
      </Collapsible.Indicator>
    </Collapsible.Trigger>
    <Collapsible.Content>
      <ul class="grid gap-2xs px-sm pt-xs pb-sm">
        {#each split.passed as flag (flag)}
          <li class="flex items-center gap-xs text-sm text-muted-foreground">
            <Check class="size-4 shrink-0 text-success" aria-hidden="true" />
            {RULES[flag].check}
          </li>
        {/each}
      </ul>
    </Collapsible.Content>
  </Collapsible.Root>
</section>
