<script lang="ts">
  import "../styles/index.css";
  import favicon from "#lib/assets/favicon.svg";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { apiMode } from "#lib/api/index.js";
  import Badge from "#lib/components/Badge.svelte";
  import ShieldCheck from "@lucide/svelte/icons/shield-check";
  import type { LayoutProps } from "./$types";

  let { children }: LayoutProps = $props();

  const links = [
    { href: "/", label: "Review" },
    { href: "/audit", label: "Audit log" },
    { href: "/chat", label: "Chat" },
  ] as const;
  const mode = apiMode();
</script>

<svelte:head>
  <link rel="icon" href={favicon} />
  <title>Memory Quarantine</title>
</svelte:head>

<div class="min-h-dvh bg-background font-content text-foreground">
  <header class="border-b border-border bg-card">
    <div class="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-md gap-y-xs px-md py-sm">
      <a href={resolve("/")} class="flex items-center gap-xs font-title font-semibold">
        <ShieldCheck class="size-5 text-primary" aria-hidden="true" />
        Memory Quarantine
      </a>
      <nav aria-label="Primary" class="flex flex-wrap items-center gap-xs">
        {#each links as link (link.href)}
          {@const current = page.url.pathname.replace(/\/$/, "") === resolve(link.href).replace(/\/$/, "")}
          <a
            href={resolve(link.href)}
            aria-current={current ? "page" : undefined}
            class="rounded-md px-sm py-xs text-sm font-medium hover:bg-accent hover:text-accent-foreground aria-[current=page]:bg-accent aria-[current=page]:text-accent-foreground"
          >
            {link.label}
          </a>
        {/each}
        {#if mode === "mock"}
          <Badge tone="outline">Mock data</Badge>
        {/if}
      </nav>
    </div>
  </header>
  <main class="mx-auto max-w-7xl px-md py-lg">
    {@render children()}
  </main>
</div>
