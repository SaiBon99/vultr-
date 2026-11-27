<script lang="ts">
  import Ban from "@lucide/svelte/icons/ban";
  import CircleAlert from "@lucide/svelte/icons/circle-alert";
  import CircleCheck from "@lucide/svelte/icons/circle-check";
  import Lock from "@lucide/svelte/icons/lock";
  import type { Verdict } from "#lib/api/index.js";
  import Badge from "./Badge.svelte";
  import { verdictLabel, verdictTone } from "./display.js";

  let { verdict }: { verdict: Verdict } = $props();
  const icons = { ALLOW: CircleCheck, NEEDS_REVIEW: CircleAlert, BLOCKED: Ban, FAIL_CLOSED: Lock };
  const Icon = $derived(icons[verdict]);
</script>

<Badge tone={verdictTone[verdict]}>
  <Icon class="size-3.5" aria-hidden="true" />
  {verdictLabel[verdict]}
</Badge>
