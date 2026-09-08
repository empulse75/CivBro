<script lang="ts">
  import { imgSrc } from "./paths.ts";
  import { lazyVideo } from "./actions.ts";

  interface Props {
    images: Array<{ url: string; type?: string }>;
    activeIdx: number;
    onprev: () => void;
    onnext: () => void;
    onopenLb: (globalIndex: number) => void;
  }

  let { images, activeIdx, onprev, onnext, onopenLb }: Props = $props();

  let pageStart = $derived(Math.max(0, Math.min(activeIdx, Math.max(0, images.length - 4))));
  let heroes = $derived(images.slice(pageStart, pageStart + 4));
</script>

{#if heroes.length > 0}
  <div class="relative">
    <div class="grid grid-cols-4 gap-3.5">
      {#each heroes as img, i (img.url)}
        {@const globalIdx = pageStart + i}
        {@const isActive = globalIdx === activeIdx}
        <button
          class="group relative aspect-[2/3] rounded-xl overflow-hidden bg-[var(--civ-panel-raised,#1a2636)] border transition-all duration-300 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--civ-accent,#67e8c6)]
            {isActive ? 'border-[var(--civ-accent,#67e8c6)] shadow-[0_0_20px_-2px_rgba(103,232,198,0.5)] scale-[1.02]' : 'border-[var(--civ-border,rgba(42,58,78,0.6))] hover:border-white/40 hover:scale-[1.01]'}"
          onclick={() => onopenLb(globalIdx)}
          aria-label={`Open image ${globalIdx + 1}`}
        >
          {#if img.type === "video"}
            <video use:lazyVideo={img.url} loop muted playsinline preload="none" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"></video>
            <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-md rounded-full p-1 text-white border border-white/20">
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
            </div>
          {:else}
            <img alt="" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" decoding="async" src={imgSrc(img, 450)} loading="lazy" />
          {/if}
          <div class="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-none">
            <span class="bg-black/60 backdrop-blur-md text-white text-xs font-semibold px-2.5 py-1 rounded-full border border-white/20 shadow-md">Expand</span>
          </div>
        </button>
      {/each}
    </div>

    {#if activeIdx > 0}
      <button
        class="absolute left-2 top-[46%] -translate-y-1/2 w-10 h-10 rounded-full bg-black/60 backdrop-blur-md border border-white/20 text-[#ecf4fb] hover:bg-[var(--civ-accent,#67e8c6)] hover:border-[var(--civ-accent,#67e8c6)] hover:text-[#0b1018] flex items-center justify-center shadow-lg transition-all active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--civ-accent,#67e8c6)]"
        onclick={onprev}
        aria-label="Previous image"
      >
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
      </button>
    {/if}
    {#if activeIdx < images.length - 1}
      <button
        class="absolute right-2 top-[46%] -translate-y-1/2 w-10 h-10 rounded-full bg-black/60 backdrop-blur-md border border-white/20 text-[#ecf4fb] hover:bg-[var(--civ-accent,#67e8c6)] hover:border-[var(--civ-accent,#67e8c6)] hover:text-[#0b1018] flex items-center justify-center shadow-lg transition-all active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--civ-accent,#67e8c6)]"
        onclick={onnext}
        aria-label="Next image"
      >
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
      </button>
    {/if}
    <div class="absolute bottom-2.5 left-2.5 text-[11px] font-bold text-[#ecf4fb] bg-black/65 backdrop-blur-md px-3 py-1 rounded-full border border-white/15 shadow-md">{activeIdx + 1} / {images.length}</div>
  </div>
{:else}
  <div class="h-[420px] flex items-center justify-center text-[var(--civ-muted,#a0b2c6)] text-sm border border-[var(--civ-border,rgba(42,58,78,0.6))] rounded-2xl bg-[var(--civ-panel,#131c29)]">No preview images</div>
{/if}
