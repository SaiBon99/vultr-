<script lang="ts">
  import { Dialog } from "@ark-ui/svelte/dialog";
  import { Portal } from "@ark-ui/svelte/portal";
  import {
    describeError,
    getApi,
    type DecideRequest,
    type DecideResponse,
    type QuarantineItem,
  } from "#lib/api/index.js";
  import { reasonRequired } from "#lib/review.js";

  let { item, ondecided }: { item: QuarantineItem; ondecided: (res: DecideResponse) => void } = $props();

  let reason = $state("");
  let busy = $state<DecideRequest["action"] | null>(null);
  let reasonError = $state<string | null>(null);
  let error = $state<string | null>(null);
  let confirmOpen = $state(false);
  const required = $derived(reasonRequired(item.verdict));
  const fieldId = $derived(`reason-${item.id}`);

  async function decide(action: DecideRequest["action"]) {
    error = null;
    reasonError = null;
    const trimmed = reason.trim();
    if (action === "override" && required && !trimmed) {
      reasonError = "Type why this row is safe. Blocked and fail-closed rows need a reason to override.";
      document.getElementById(fieldId)?.focus();
      return;
    }
    busy = action;
    let res: DecideResponse;
    try {
      res = await getApi().decide(item.id, trimmed ? { action, reason: trimmed } : { action });
    } catch (err) {
      const message = describeError(err, "The decision failed. Try again.");
      if (action === "override" && message.includes("reason_required")) reasonError = message;
      else error = message;
      confirmOpen = false;
      busy = null;
      return;
    }
    // Close the dialog before the parent swaps this panel out, so its portal unmounts cleanly.
    busy = null;
    confirmOpen = false;
    await new Promise((r) => setTimeout(r, 0));
    ondecided(res);
  }

  const button = "h-control rounded-md px-md text-sm font-medium focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:bg-muted disabled:text-muted-foreground";
</script>

<section aria-labelledby="decide-title" class="grid gap-sm rounded-lg border border-border p-md" data-testid="decision">
  <h3 id="decide-title" class="font-title text-base font-semibold">Decision</h3>

  <div class="grid gap-2xs">
    <label for={fieldId} class="text-sm font-medium">
      Override reason <span class="font-normal text-muted-foreground">({required ? "required" : "optional"})</span>
    </label>
    <textarea
      id={fieldId}
      bind:value={reason}
      maxlength="1000"
      rows="2"
      aria-invalid={reasonError ? "true" : undefined}
      aria-describedby="{fieldId}-hint"
      class="rounded-md border bg-background px-sm py-xs text-sm focus-visible:ring-2 focus-visible:ring-ring {reasonError
        ? 'border-destructive'
        : 'border-input'}"
    ></textarea>
    {#if reasonError}
      <p id="{fieldId}-hint" class="text-sm text-destructive" role="alert">{reasonError}</p>
    {:else}
      <p id="{fieldId}-hint" class="text-sm text-muted-foreground">
        Override promotes the write into memory as external_override. The reason is signed into the receipt.
      </p>
    {/if}
  </div>

  <div class="flex flex-wrap gap-sm">
    <Dialog.Root bind:open={confirmOpen} role="alertdialog">
      <Dialog.Trigger disabled={busy !== null} class="{button} bg-destructive text-destructive-foreground hover:opacity-90">
        Purge
      </Dialog.Trigger>
      <Portal>
        <Dialog.Backdrop class="fixed inset-0 z-40 bg-foreground/40" />
        <Dialog.Positioner class="fixed inset-0 z-50 grid place-items-center p-md">
          <Dialog.Content class="grid w-full max-w-md gap-md rounded-xl bg-popover p-lg text-popover-foreground shadow-lg">
            <div class="grid gap-xs">
              <Dialog.Title class="font-title text-lg font-semibold">Purge this write?</Dialog.Title>
              <Dialog.Description class="text-sm text-pretty text-muted-foreground">
                The content is deleted for good. The hash and embedding stay, so a similar write is caught next time.
                A signed receipt records the decision.
              </Dialog.Description>
            </div>
            <div class="flex justify-end gap-sm">
              <Dialog.CloseTrigger class="{button} bg-secondary text-secondary-foreground hover:bg-accent">Cancel</Dialog.CloseTrigger>
              <button
                type="button"
                disabled={busy !== null}
                onclick={() => decide("purge")}
                class="{button} bg-destructive text-destructive-foreground hover:opacity-90"
              >
                {busy === "purge" ? "Purging…" : "Purge and sign"}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Positioner>
      </Portal>
    </Dialog.Root>
    <button
      type="button"
      disabled={busy !== null}
      onclick={() => decide("override")}
      class="{button} bg-secondary text-secondary-foreground hover:bg-accent hover:text-accent-foreground"
    >
      {busy === "override" ? "Overriding…" : "Override"}
    </button>
  </div>
  {#if error}<p class="text-sm text-destructive" role="alert">{error}</p>{/if}
</section>
