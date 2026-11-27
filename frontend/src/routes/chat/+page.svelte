<script lang="ts">
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import BookOpen from "@lucide/svelte/icons/book-open";
  import Brain from "@lucide/svelte/icons/brain";
  import CircleAlert from "@lucide/svelte/icons/circle-alert";
  import Globe from "@lucide/svelte/icons/globe";
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import Mail from "@lucide/svelte/icons/mail";
  import ShoppingCart from "@lucide/svelte/icons/shopping-cart";
  import Sparkles from "@lucide/svelte/icons/sparkles";
  import SquarePen from "@lucide/svelte/icons/square-pen";
  import { tick } from "svelte";
  import { resolve } from "$app/paths";
  import {
    ApiError,
    describeError,
    getApi,
    getReviewerToken,
    setReviewerToken,
    type ChatDoneEvent,
    type ChatEvent,
    type ChatRunEvent,
    type ChatSession,
    type ChatStepEvent,
  } from "#lib/api/index.js";
  import ChatStep from "#lib/components/ChatStep.svelte";
  import RunLog from "#lib/components/RunLog.svelte";

  interface TurnError {
    message: string;
    /** HTTP status of a pre-stream refusal; 0 for stream errors. */
    status: number;
    runId: string | null;
  }

  interface Turn {
    id: number;
    message: string;
    running: boolean;
    run: ChatRunEvent | null;
    steps: ChatStepEvent[];
    reply: string | null;
    done: ChatDoneEvent | null;
    error: TurnError | null;
  }

  const STARTER = "Order 2 reams of A4 copy paper from https://shop.example.com/a4-paper";
  const MAX_LENGTH = 2000;

  const tools = [
    { icon: Globe, name: "Browse", policy: "Reads any public page through the host and marks the session tainted." },
    { icon: Brain, name: "Remember", policy: "Every note goes through the gate. Anything not allowed waits in quarantine." },
    { icon: BookOpen, name: "Recall", policy: "Reads approved memories only, never quarantined ones." },
    { icon: ShoppingCart, name: "Place order", policy: "Always simulated. Nothing is bought or charged." },
    { icon: Mail, name: "Send email", policy: "Always refused. The sandbox has no outbound mail." },
  ];

  let turns = $state<Turn[]>([]);
  let chat = $state<ChatSession | null>(null);
  let draft = $state("");
  let running = $state(false);
  let token = $state(getReviewerToken() ?? "");
  let composer = $state<HTMLTextAreaElement>();
  let controller: AbortController | null = null;
  let nextId = 0;

  const canSend = $derived(!running && draft.trim().length > 0);

  /** Keeps the newest event in view when the reader was already at the bottom. */
  async function follow() {
    const el = document.scrollingElement;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 160;
    await tick();
    if (atBottom) el.scrollTop = el.scrollHeight;
  }

  function apply(turn: Turn, event: ChatEvent) {
    switch (event.type) {
      case "run":
        turn.run = event;
        break;
      case "step":
        turn.steps.push(event);
        break;
      case "reply":
        turn.reply = event.text;
        break;
      case "done":
        turn.done = event;
        break;
      case "error":
        turn.error = { message: `${event.detail} (${event.code})`, status: 0, runId: event.run_id };
        break;
    }
  }

  async function send(text: string) {
    const message = text.trim();
    if (!message || running) return;
    draft = "";
    turns.push({ id: nextId++, message, running: true, run: null, steps: [], reply: null, done: null, error: null });
    const turn = turns[turns.length - 1];
    const ctrl = new AbortController();
    controller = ctrl;
    running = true;
    await follow();
    try {
      const api = getApi();
      const session = chat ?? (await api.createChat());
      if (ctrl.signal.aborted) return;
      chat = session;
      for await (const event of api.sendChatMessage(session.chat_id, message, { signal: ctrl.signal })) {
        if (ctrl.signal.aborted) return;
        apply(turn, event);
        await follow();
      }
      if (!turn.done && !turn.error)
        turn.error = { message: "The stream ended before the agent finished.", status: 0, runId: turn.run?.run_id ?? null };
    } catch (err) {
      if (ctrl.signal.aborted) return;
      turn.error = {
        message: describeError(err, "The message could not be sent. Try again."),
        status: err instanceof ApiError ? err.status : 0,
        runId: turn.run?.run_id ?? null,
      };
    } finally {
      turn.running = false;
      if (controller === ctrl) {
        controller = null;
        running = false;
      }
    }
  }

  function onsubmit(event: SubmitEvent) {
    event.preventDefault();
    void send(draft);
  }

  function onkeydown(event: KeyboardEvent) {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    if (canSend) void send(draft);
  }

  function sendStarter() {
    composer?.focus();
    void send(STARTER);
  }

  function retry(turn: Turn) {
    turns = turns.filter((t) => t.id !== turn.id);
    composer?.focus();
    void send(turn.message);
  }

  function saveTokenAndRetry(event: SubmitEvent, turn: Turn) {
    event.preventDefault();
    setReviewerToken(token.trim() || null);
    retry(turn);
  }

  /** Starts over with a fresh chat and memory session; the open stream is dropped. */
  function newChat() {
    controller?.abort();
    controller = null;
    running = false;
    turns = [];
    chat = null;
    draft = "";
    composer?.focus();
  }

  const seconds = (ms: number) => `${(ms / 1000).toFixed(1)} s`;
</script>

<svelte:head>
  <title>Shopping agent · Memory Quarantine</title>
</svelte:head>

<div class="flex flex-wrap items-end justify-between gap-md">
  <div class="grid max-w-prose gap-2xs">
    <h1 class="font-title text-2xl font-semibold text-balance">Shopping agent</h1>
    <p class="text-pretty text-muted-foreground">
      Give the agent a task on a public website. Each message runs in a disposable sandbox with no network; the host
      fetches pages, gates every memory write and simulates checkout.
    </p>
  </div>
  {#if turns.length > 0}
    <button
      type="button"
      onclick={newChat}
      class="flex h-control items-center gap-xs rounded-md bg-secondary px-md text-sm font-medium text-secondary-foreground hover:bg-accent hover:text-accent-foreground focus-visible:ring-2 focus-visible:ring-ring"
    >
      <SquarePen class="size-4" aria-hidden="true" />
      New chat
    </button>
  {/if}
</div>

<div class="mt-lg grid items-start gap-lg lg:grid-cols-3">
  <div class="grid gap-lg lg:col-span-2">
    <section aria-label="Conversation" class="grid gap-xl">
      {#if turns.length === 0}
        <div class="grid justify-items-start gap-sm rounded-lg border border-border bg-card p-lg">
          <p class="font-medium">No messages yet</p>
          <p class="max-w-prose text-sm text-pretty text-muted-foreground">
            Ask the agent to buy something from a shop page. This sample page hides an instruction to leak card details;
            watch the gate freeze it while the order still goes through.
          </p>
          <button
            type="button"
            onclick={sendStarter}
            class="flex min-h-control items-center gap-xs rounded-md bg-secondary px-md py-xs text-left text-sm font-medium text-secondary-foreground hover:bg-accent hover:text-accent-foreground focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Sparkles class="size-4 shrink-0" aria-hidden="true" />
            {STARTER}
          </button>
        </div>
      {/if}

      {#each turns as turn (turn.id)}
        <article class="grid gap-md" data-testid="chat-turn" aria-busy={turn.running}>
          <div class="grid justify-items-end">
            <p class="max-w-prose rounded-lg bg-muted px-md py-sm text-pretty break-words whitespace-pre-wrap">
              <span class="sr-only">You: </span>{turn.message}
            </p>
          </div>

          <div class="grid gap-md" aria-live="polite">
            <h2 class="sr-only">Agent steps</h2>
            {#if turn.steps.length > 0 || turn.running}
              <ol class="grid">
                {#each turn.steps as step (step.index)}
                  <ChatStep {step} />
                {/each}
                {#if turn.running && !turn.reply}
                  <li class="flex items-center gap-sm text-sm text-muted-foreground" data-testid="chat-working">
                    <span class="grid size-8 shrink-0 place-items-center rounded-md bg-muted">
                      <LoaderCircle class="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                    </span>
                    {turn.run ? "Agent is working" : "Starting the sandbox"}
                  </li>
                {/if}
              </ol>
            {/if}

            {#if turn.reply}
              <p class="max-w-prose text-pretty break-words whitespace-pre-wrap" data-testid="chat-reply">
                <span class="sr-only">Agent: </span>{turn.reply}
              </p>
            {/if}

            {#if turn.error}
              <div role="alert" class="grid justify-items-start gap-sm rounded-lg border border-destructive bg-card p-md">
                <p class="flex items-start gap-xs text-sm">
                  <CircleAlert class="mt-2xs size-4 shrink-0 text-destructive" aria-hidden="true" />
                  <span><span class="font-medium text-destructive">The agent stopped.</span> {turn.error.message}</span>
                </p>
                {#if turn.error.status === 401}
                  <form class="flex flex-wrap items-end gap-sm" onsubmit={(e) => saveTokenAndRetry(e, turn)}>
                    <div class="grid gap-2xs">
                      <label class="text-sm font-medium" for="chat-token-{turn.id}">Reviewer token</label>
                      <input
                        id="chat-token-{turn.id}"
                        type="password"
                        autocomplete="off"
                        bind:value={token}
                        class="h-control rounded-md border border-input bg-background px-md focus-visible:ring-2 focus-visible:ring-ring"
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={running}
                      class="h-control rounded-md bg-secondary px-md text-sm font-medium text-secondary-foreground hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring disabled:text-muted-foreground"
                    >
                      Save and retry
                    </button>
                  </form>
                {:else if !running && turn.id === turns[turns.length - 1]?.id}
                  <button
                    type="button"
                    onclick={() => retry(turn)}
                    class="h-control rounded-md bg-secondary px-md text-sm font-medium text-secondary-foreground hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    Try again
                  </button>
                {/if}
              </div>
            {/if}

            {#if turn.done}
              {@const limits = turn.done.sandbox.limits}
              <p class="text-xs text-pretty text-muted-foreground" data-testid="chat-done">
                Sandbox network {turn.done.sandbox.network}, capped at {limits.memory_mb} MB, {limits.cpus} CPU and
                {limits.timeout_s} s, then removed. {seconds(turn.done.elapsed_ms)}, {turn.done.steps}
                {turn.done.steps === 1 ? "step" : "steps"}, {turn.done.model}.
              </p>
            {/if}
          </div>

          {#if turn.done?.log_uri}
            <RunLog runId={turn.done.run_id} source="chat" />
          {:else if turn.error?.runId && !turn.running}
            <RunLog runId={turn.error.runId} source="chat" />
          {/if}
        </article>
      {/each}
    </section>

    <form
      class="sticky bottom-0 grid gap-2xs border-t border-border bg-background pt-sm"
      style="padding-bottom: max(var(--spacing-md), env(safe-area-inset-bottom))"
      {onsubmit}
    >
      <label class="text-sm font-medium" for="chat-message">Task for the agent</label>
      <div class="flex items-end gap-xs">
        <textarea
          id="chat-message"
          bind:this={composer}
          bind:value={draft}
          {onkeydown}
          rows="2"
          maxlength={MAX_LENGTH}
          aria-describedby="chat-hint"
          class="field-sizing-content max-h-48 min-w-0 flex-1 resize-none rounded-md border border-input bg-background px-md py-xs focus-visible:ring-2 focus-visible:ring-ring"
        ></textarea>
        <button
          type="submit"
          disabled={!canSend}
          class="flex h-control shrink-0 items-center gap-xs rounded-md bg-primary px-md text-sm font-medium text-primary-foreground disabled:bg-muted disabled:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ArrowUp class="size-4" aria-hidden="true" />
          Send
        </button>
      </div>
      <p id="chat-hint" class="text-xs text-muted-foreground">
        {running ? "The agent is working on your last message." : "Enter sends, Shift+Enter adds a new line."}
      </p>
    </form>
  </div>

  <aside aria-labelledby="chat-tools-title" class="grid gap-md rounded-lg border border-border bg-card p-lg lg:sticky lg:top-md">
    <h2 id="chat-tools-title" class="font-title text-base font-semibold">What the agent can reach</h2>
    <ul class="grid gap-sm">
      {#each tools as tool (tool.name)}
        <li class="flex gap-sm">
          <tool.icon class="mt-2xs size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span class="grid gap-2xs text-sm">
            <span class="font-medium">{tool.name}</span>
            <span class="text-pretty text-muted-foreground">{tool.policy}</span>
          </span>
        </li>
      {/each}
    </ul>
    {#if chat}
      <div class="grid gap-2xs border-t border-border pt-md text-sm">
        <span class="text-muted-foreground">Memory session</span>
        <span class="font-mono text-xs break-all" data-testid="chat-session-id">{chat.session_id}</span>
        <a href={resolve("/")} class="justify-self-start rounded-sm font-medium underline decoration-primary underline-offset-4 hover:decoration-2 focus-visible:ring-2 focus-visible:ring-ring">
          Open the review queue
        </a>
      </div>
    {/if}
  </aside>
</div>
