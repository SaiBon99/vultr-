<script lang="ts">
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import ShieldCheck from "@lucide/svelte/icons/shield-check";
  import ShieldX from "@lucide/svelte/icons/shield-x";
  import { getApi, type PublicKey, type Receipt } from "#lib/api/index.js";
  import { verifyReceipt } from "#lib/crypto/verifyReceipt.js";
  import { formatTime, shortHash } from "#lib/format.js";

  let { receipt }: { receipt: Receipt } = $props();

  let key = $state<PublicKey | null>(null);
  let valid = $state<boolean | null>(null);
  let tampered = $state<boolean | null>(null);
  let keyError = $state(false);

  $effect(() => {
    const current = receipt;
    valid = null;
    tampered = null;
    keyError = false;
    getApi()
      .getPublicKey()
      .then(async (k) => {
        key = k;
        const ok = await verifyReceipt(current, k);
        if (current === receipt) valid = ok;
      })
      .catch(() => (keyError = true));
  });

  async function tamperTest() {
    if (!key) return;
    tampered = await verifyReceipt({ ...receipt, risk_score: receipt.risk_score === 0 ? 1 : receipt.risk_score - 1 }, key);
  }

  const timestamp = $derived(formatTime(receipt.timestamp));
</script>

<section aria-labelledby="receipt-title" class="grid gap-sm rounded-lg border border-border p-md" data-testid="receipt">
  <h3 id="receipt-title" class="font-title text-base font-semibold">
    Signed receipt, {receipt.event}
  </h3>

  <div aria-live="polite" class="flex items-start gap-xs text-sm" data-testid="receipt-status">
    {#if keyError}
      <ShieldX class="mt-2xs size-4 shrink-0 text-destructive" aria-hidden="true" />
      <p>Could not load the public key, so the signature is unverified.</p>
    {:else if valid === null}
      <LoaderCircle class="mt-2xs size-4 shrink-0 animate-spin motion-reduce:animate-none" aria-hidden="true" />
      <p>Verifying the Ed25519 signature in this browser.</p>
    {:else if valid}
      <ShieldCheck class="mt-2xs size-4 shrink-0 text-success" aria-hidden="true" />
      <p>
        <span class="font-medium">Signature valid.</span>
        <span class="text-muted-foreground">Verified in this browser with Ed25519 key {key?.key_id}.</span>
      </p>
    {:else}
      <ShieldX class="mt-2xs size-4 shrink-0 text-destructive" aria-hidden="true" />
      <p>
        <span class="font-medium">Signature invalid.</span>
        <span class="text-muted-foreground">The receipt does not match key {key?.key_id}.</span>
      </p>
    {/if}
  </div>

  <dl class="grid gap-x-md gap-y-2xs text-sm sm:grid-cols-2">
    <div class="grid">
      <dt class="text-muted-foreground">Receipt</dt>
      <dd class="font-mono break-all">{receipt.receipt_id}</dd>
    </div>
    <div class="grid">
      <dt class="text-muted-foreground">Signed</dt>
      <dd>{timestamp}</dd>
    </div>
    <div class="grid">
      <dt class="text-muted-foreground">Payload hash</dt>
      <dd class="font-mono">{shortHash(receipt.payload_hash)}</dd>
    </div>
    <div class="grid">
      <dt class="text-muted-foreground">Audit head</dt>
      <dd class="font-mono">{shortHash(receipt.audit_head_hash)}</dd>
    </div>
    {#if receipt.override_reason}
      <div class="grid sm:col-span-2">
        <dt class="text-muted-foreground">Override reason</dt>
        <dd>{receipt.override_reason}</dd>
      </div>
    {/if}
  </dl>

  {#if valid}
    <div class="flex flex-wrap items-center gap-sm">
      <button
        type="button"
        onclick={tamperTest}
        class="h-control rounded-md bg-secondary px-md text-sm font-medium text-secondary-foreground hover:bg-accent hover:text-accent-foreground focus-visible:ring-2 focus-visible:ring-ring"
      >
        Verify a tampered copy
      </button>
      {#if tampered !== null}
        <p class="text-sm" aria-live="polite">
          {tampered ? "Tampered copy verified, which should not happen." : "Tampered copy rejected: risk_score changed by 1."}
        </p>
      {/if}
    </div>
  {/if}
</section>
