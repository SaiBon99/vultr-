<script lang="ts">
  import ArrowUpRight from "@lucide/svelte/icons/arrow-up-right";
  import BookOpen from "@lucide/svelte/icons/book-open";
  import Brain from "@lucide/svelte/icons/brain";
  import CircleAlert from "@lucide/svelte/icons/circle-alert";
  import CircleCheck from "@lucide/svelte/icons/circle-check";
  import FlaskConical from "@lucide/svelte/icons/flask-conical";
  import Globe from "@lucide/svelte/icons/globe";
  import Mail from "@lucide/svelte/icons/mail";
  import ShieldCheck from "@lucide/svelte/icons/shield-check";
  import ShoppingCart from "@lucide/svelte/icons/shopping-cart";
  import { resolve } from "$app/paths";
  import type { ChatStepEvent } from "#lib/api/index.js";
  import Badge from "./Badge.svelte";
  import VerdictBadge from "./VerdictBadge.svelte";
  import { toolLabel } from "./display.js";

  let { step }: { step: ChatStepEvent } = $props();

  const icons = {
    browse: Globe,
    remember: Brain,
    recall: BookOpen,
    place_order: ShoppingCart,
    send_email: Mail,
  };
  const Icon = $derived(icons[step.tool]);
  const detail = $derived(step.detail);
  /** send_email is always refused by design: the attempt was contained, nothing failed. */
  const contained = $derived(step.tool === "send_email" && step.status === "refused");
</script>

<li class="group relative flex gap-sm pb-md last:pb-0" data-testid="chat-step" data-tool={step.tool}>
  <span class="absolute start-4 top-9 bottom-1 w-px bg-border group-last:hidden" aria-hidden="true"></span>
  <span class="grid size-8 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground">
    <Icon class="size-4" aria-hidden="true" />
  </span>
  <div class="grid min-w-0 flex-1 gap-2xs pt-2xs">
    <div class="flex flex-wrap items-center justify-between gap-x-sm gap-y-2xs">
      <span class="text-sm font-medium">{toolLabel[step.tool]}</span>
      <span class="flex flex-wrap items-center gap-xs">
        {#if detail?.kind === "browse" && detail.session_tainted}
          <Badge tone="warning">Session tainted</Badge>
        {/if}
        {#if detail?.kind === "place_order" && detail.simulated}
          <Badge tone="outline">
            <FlaskConical class="size-3.5" aria-hidden="true" />
            Simulated
          </Badge>
        {/if}
        {#if contained}
          <Badge tone="info">
            <ShieldCheck class="size-3.5" aria-hidden="true" />
            Egress contained
          </Badge>
        {:else if step.status === "refused"}
          <Badge tone="neutral">Refused{step.error_code ? ` (${step.error_code})` : ""}</Badge>
        {:else if step.status === "error"}
          <Badge tone="danger">
            <CircleAlert class="size-3.5" aria-hidden="true" />
            Failed{step.error_code ? ` (${step.error_code})` : ""}
          </Badge>
        {:else}
          <span class="flex items-center gap-2xs text-xs text-muted-foreground">
            <CircleCheck class="size-3.5 text-success" aria-hidden="true" />
            Done
          </span>
        {/if}
      </span>
    </div>
    <p class="text-sm text-pretty break-words">{step.summary}</p>

    {#if detail?.kind === "remember"}
      <blockquote class="border-s-2 border-border ps-sm text-sm text-muted-foreground text-pretty line-clamp-3 break-words">
        {detail.content}
      </blockquote>
      <div class="flex flex-wrap items-center gap-xs">
        <VerdictBadge verdict={detail.verdict} />
        <span class="text-xs font-medium tabular-nums">Risk {detail.risk_score}<span class="sr-only"> of 100</span></span>
        {#if detail.table === "quarantine_queue"}
          <a
            href="{resolve('/')}?item={encodeURIComponent(detail.id)}"
            class="ms-auto flex items-center gap-2xs rounded-sm text-sm font-medium underline decoration-primary underline-offset-4 hover:decoration-2 focus-visible:ring-2 focus-visible:ring-ring"
          >
            Open in review
            <ArrowUpRight class="size-4" aria-hidden="true" />
          </a>
        {/if}
      </div>
    {/if}
  </div>
</li>
