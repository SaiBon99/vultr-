<script lang="ts">
  import type { Snippet } from "svelte";

  type Tone = "danger" | "warning" | "info" | "success" | "neutral" | "outline";
  let { tone = "neutral", children }: { tone?: Tone; children: Snippet } = $props();

  const tones: Record<Tone, string> = {
    danger: "bg-destructive text-destructive-foreground",
    warning: "bg-warning text-warning-foreground",
    info: "bg-info text-info-foreground",
    success: "bg-success text-success-foreground",
    neutral: "bg-secondary text-secondary-foreground",
    outline: "border border-border text-muted-foreground",
  };
</script>

<span
  class="inline-flex items-center gap-2xs rounded-sm px-xs py-2xs text-xs font-medium whitespace-nowrap {tones[
    tone
  ]}"
>
  {@render children()}
</span>
