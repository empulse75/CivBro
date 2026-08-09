<script lang="ts">
  import { imgSrc } from "./paths.ts";
  import { fmtCount } from "./format.ts";

  interface Props {
    images: Array<{ url: string; type: string; nsfwLevel?: number; width?: number; height?: number; meta?: Record<string, unknown>; name?: string }>;
    initialIndex: number;
    onclose: () => void;
  }

  let { images, initialIndex, onclose }: Props = $props();

  let idx = $state(0);

  $effect(() => {
    idx = Math.min(Math.max(initialIndex, 0), Math.max(images.length - 1, 0));
  });

  function prev() { if (idx > 0) idx--; }
  function next() { if (idx < images.length - 1) idx++; }

  function handleKey(e: KeyboardEvent) {
    if (e.key === "Escape") onclose();
    else if (e.key === "ArrowLeft") prev();
    else if (e.key === "ArrowRight") next();
  }
</script>

<svelte:window onkeydown={handleKey} />

<div
  class="fixed inset-0 z-[60] bg-black flex"
  onclick={onclose}
  onkeydown={handleKey}
  role="dialog"
  aria-modal="true"
  tabindex="-1"
>
  <!-- Left: image viewer -->
  <div class="flex-1 flex items-center justify-center relative" onclick={(e: MouseEvent) => e.stopPropagation()}>
    <button
      class="absolute top-4 right-4 text-white/40 hover:text-white z-10 w-10 h-10 rounded-full bg-white/5 hover:bg-white/10 flex items-center justify-center"
      onclick={onclose}
      aria-label="Close"
    >
      <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="5" x2="19" y2="19"/><line x1="19" y1="5" x2="5" y2="19"/></svg>
    </button>

    {#if images.length > 1}
      <button
        class="absolute left-4 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full bg-white/5 hover:bg-white/10 text-white flex items-center justify-center transition-all z-10 {idx === 0 ? 'opacity-20' : ''}"
        onclick={(e: MouseEvent) => { e.stopPropagation(); prev(); }}
        aria-label="Previous image"
      >
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
      </button>
      <button
        class="absolute right-4 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full bg-white/5 hover:bg-white/10 text-white flex items-center justify-center transition-all z-10 {idx >= images.length - 1 ? 'opacity-20' : ''}"
        onclick={(e: MouseEvent) => { e.stopPropagation(); next(); }}
        aria-label="Next image"
      >
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
      </button>
    {/if}

    {#if images[idx]?.type === "video"}
      <video src={images[idx].url} autoplay loop muted playsinline controls class="max-w-full max-h-[92vh] object-contain z-0 rounded-lg"></video>
    {:else if images[idx]}
      <img alt="" class="max-w-full max-h-[92vh] object-contain z-0 rounded-lg" src={imgSrc(images[idx], 1600)} onclick={(e: MouseEvent) => e.stopPropagation()} />
    {/if}

    {#if images.length > 1}
      <div class="absolute bottom-6 left-1/2 -translate-x-1/2 text-sm text-white/30">{idx + 1}/{fmtCount(images.length)}</div>
    {/if}
  </div>

  <!-- Right: metadata panel -->
  <div class="w-[320px] shrink-0 border-l border-white/10 bg-[#0a0a0a] flex flex-col overflow-y-auto p-4 gap-4" onclick={(e: MouseEvent) => e.stopPropagation()}>
    {#if images[idx]}
      {@const img = images[idx]}
    {#if img?.width && img?.height}
      <div>
        <h3 class="text-[11px] font-semibold text-[#909296] uppercase tracking-[0.1em] mb-2">Resolution</h3>
        <p class="text-[14px] text-[#c1c2c5] font-medium">{img.width} × {img.height}</p>
      </div>
    {/if}
    {#if img?.type}
      <div>
        <h3 class="text-[11px] font-semibold text-[#909296] uppercase tracking-[0.1em] mb-2">Type</h3>
        <span class="text-[12px] font-bold uppercase tracking-wide text-[#c1c2c5] bg-white/5 border border-white/10 px-2 py-1 rounded">{img.type}</span>
      </div>
    {/if}
    {#if img?.meta && Object.keys(img.meta).length > 0}
      <div>
        <h3 class="text-[11px] font-semibold text-[#909296] uppercase tracking-[0.1em] mb-2">Generation Data</h3>
        <div class="text-[12px] text-[#a1a1aa] space-y-1.5">
          {#each Object.entries(img.meta) as [k, v]}
            {#if v && k !== "resources" && k !== "hashes"}
              <div class="flex justify-between gap-2">
                <span class="text-[#5c5f66] capitalize">{k.replace(/([A-Z])/g, ' $1').trim()}</span>
                <span class="text-[#c1c2c5] text-right truncate">{String(v)}</span>
              </div>
            {/if}
          {/each}
        </div>
      </div>
    {/if}
    {/if}
  </div>
</div>
