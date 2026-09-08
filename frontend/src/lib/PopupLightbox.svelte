<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { imgSrc } from "./paths.ts";
  import { fmtCount } from "./format.ts";

  interface Props {
    images: Array<{ url: string; type: string; nsfwLevel?: number; width?: number; height?: number; meta?: Record<string, unknown>; name?: string }>;
    initialIndex: number;
    onclose: () => void;
  }

  let { images, initialIndex, onclose }: Props = $props();

  let idx = $state(0);
  let previouslyFocused: HTMLElement | null = null;
  let closeBtnEl = $state<HTMLButtonElement | null>(null);
  let lightboxEl = $state<HTMLDivElement | null>(null);

  onMount(() => {
    previouslyFocused = document.activeElement as HTMLElement | null;
    closeBtnEl?.focus();
  });

  onDestroy(() => {
    if (previouslyFocused?.isConnected) previouslyFocused.focus();
  });

  $effect(() => {
    idx = Math.min(Math.max(initialIndex, 0), Math.max(images.length - 1, 0));
  });

  function prev() { if (idx > 0) idx--; }
  function next() { if (idx < images.length - 1) idx++; }

  function handleKey(e: KeyboardEvent) {
    if (e.defaultPrevented) return;
    if (e.key === "Tab" && lightboxEl) {
      const controls = Array.from(lightboxEl.querySelectorAll<HTMLElement>('button, video[controls], [href], [tabindex]'))
        .filter(el => el.tabIndex >= 0 && !el.hasAttribute("disabled") && el.getClientRects().length > 0);
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      return;
    }
    if (e.key === "Escape") onclose();
    else if (e.key === "ArrowLeft") prev();
    else if (e.key === "ArrowRight") next();
    else return;
    e.preventDefault();
  }
</script>


<div
  bind:this={lightboxEl}
  class="fixed inset-0 z-[60] bg-black/95 backdrop-blur-lg flex flex-col md:flex-row overflow-hidden"
  onclick={(e: MouseEvent) => { if (e.target === e.currentTarget) onclose(); }}
  onkeydown={(e) => { e.stopPropagation(); handleKey(e); }}
  role="dialog"
  aria-modal="true"
  aria-label="Image viewer"
  tabindex="-1"
>
  <!-- Left: image viewer -->
  <div class="flex-1 flex items-center justify-center relative p-4 min-h-0">
    <button
      bind:this={closeBtnEl}
      class="absolute top-4 right-4 text-white/70 hover:text-white z-20 w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 backdrop-blur-md flex items-center justify-center transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--civ-accent,#67e8c6)]"
      onclick={onclose}
      aria-label="Close lightbox"
    >
      <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
    </button>

    {#if images.length > 1}
      <button
        class="absolute left-4 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full bg-black/60 hover:bg-[var(--civ-accent,#67e8c6)] hover:text-[#0b1018] text-white flex items-center justify-center transition-all z-20 border border-white/15 backdrop-blur-md cursor-pointer disabled:opacity-20 disabled:pointer-events-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--civ-accent,#67e8c6)]"
        onclick={(e: MouseEvent) => { e.stopPropagation(); prev(); }}
        disabled={idx === 0}
        aria-label="Previous image"
      >
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
      </button>
      <button
        class="absolute right-4 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full bg-black/60 hover:bg-[var(--civ-accent,#67e8c6)] hover:text-[#0b1018] text-white flex items-center justify-center transition-all z-20 border border-white/15 backdrop-blur-md cursor-pointer disabled:opacity-20 disabled:pointer-events-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--civ-accent,#67e8c6)]"
        onclick={(e: MouseEvent) => { e.stopPropagation(); next(); }}
        disabled={idx >= images.length - 1}
        aria-label="Next image"
      >
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
      </button>
    {/if}

    {#if images[idx]?.type === "video"}
      <video src={images[idx].url} autoplay loop muted playsinline controls class="max-w-full max-h-full object-contain z-0 rounded-xl shadow-2xl"></video>
    {:else if images[idx]}
      <img alt="" class="max-w-full max-h-full object-contain z-0 rounded-xl shadow-2xl" src={imgSrc(images[idx], 1600)} />
    {/if}

    {#if images.length > 1}
      <div class="absolute bottom-6 left-1/2 -translate-x-1/2 text-xs font-bold text-white/90 bg-black/65 backdrop-blur-md px-3.5 py-1.5 rounded-full border border-white/15 shadow-lg">{idx + 1} / {fmtCount(images.length)}</div>
    {/if}
  </div>

  <!-- Right: metadata panel -->
  <div class="w-full md:w-[340px] max-h-[38vh] md:max-h-full shrink-0 border-t md:border-t-0 md:border-l border-[var(--civ-border,rgba(42,58,78,0.6))] bg-[var(--civ-panel,#131c29)]/90 backdrop-blur-xl flex flex-col overflow-y-auto p-5 gap-4 text-[var(--civ-ink,#ecf4fb)]">
    {#if images[idx]}
      {@const img = images[idx]}
      {#if img?.width && img?.height}
        <div class="bg-[var(--civ-panel-raised,#1a2636)] border border-white/10 rounded-xl p-3.5">
          <h3 class="text-[11px] font-bold text-[var(--civ-muted,#a0b2c6)] uppercase tracking-wider mb-1">Resolution</h3>
          <p class="text-sm text-[var(--civ-ink,#ecf4fb)] font-semibold">{img.width} × {img.height} px</p>
        </div>
      {/if}
      {#if img?.type}
        <div class="bg-[var(--civ-panel-raised,#1a2636)] border border-white/10 rounded-xl p-3.5">
          <h3 class="text-[11px] font-bold text-[var(--civ-muted,#a0b2c6)] uppercase tracking-wider mb-1.5">Type</h3>
          <span class="text-xs font-bold uppercase tracking-wider text-[var(--civ-accent,#67e8c6)] bg-[var(--civ-accent,#67e8c6)]/15 border border-[var(--civ-accent,#67e8c6)]/30 px-2.5 py-1 rounded-md inline-block">{img.type}</span>
        </div>
      {/if}
      {#if img?.meta && Object.keys(img.meta).length > 0}
        <div class="bg-[var(--civ-panel-raised,#1a2636)] border border-white/10 rounded-xl p-3.5">
          <h3 class="text-[11px] font-bold text-[var(--civ-muted,#a0b2c6)] uppercase tracking-wider mb-2.5">Generation Data</h3>
          <div class="text-xs text-[var(--civ-muted,#a0b2c6)] space-y-2">
            {#each Object.entries(img.meta) as [k, v]}
              {#if v && k !== "resources" && k !== "hashes"}
                <div class="flex justify-between gap-2 border-b border-white/5 pb-1.5 last:border-0 last:pb-0">
                  <span class="text-white/70 font-medium capitalize">{k.replace(/([A-Z])/g, ' $1').trim()}</span>
                  <span class="text-[var(--civ-ink,#ecf4fb)] font-mono text-right truncate max-w-[180px]" title={String(v)}>{String(v)}</span>
                </div>
              {/if}
            {/each}
          </div>
        </div>
      {/if}
    {/if}
  </div>
</div>
