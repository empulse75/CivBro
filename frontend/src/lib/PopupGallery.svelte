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
    <div class="grid grid-cols-4 gap-3">
      {#each heroes as img, i (img.url)}
        <button
          class="group relative aspect-[2/3] rounded-lg overflow-hidden bg-[#25262b] border transition-all
            {pageStart + i === activeIdx ? 'border-[#228be6] shadow-[0_0_18px_-2px_rgba(34,139,230,0.55)]' : 'border-[#2c2e33] hover:border-[#4a4e55]'}"
          onclick={() => onopenLb(pageStart + i)}
        >
          {#if img.type === "video"}
            <video use:lazyVideo={img.url} loop muted playsinline preload="none" class="w-full h-full object-cover"></video>
          {:else}
            <img alt="" class="w-full h-full object-cover" decoding="async" src={imgSrc(img, 450)} loading="lazy" />
          {/if}
        </button>
      {/each}
    </div>

    {#if images.length > 4}
      <button
        class="absolute left-2 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-[#1a1b1e]/80 backdrop-blur border border-[#2c2e33] text-[#e5e7eb] hover:bg-[#228be6] hover:border-[#228be6] disabled:opacity-25 disabled:pointer-events-none flex items-center justify-center shadow-lg transition-all"
        onclick={onprev}
        disabled={activeIdx === 0}
        aria-label="Previous image"
      >
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
      </button>
      <button
        class="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-[#1a1b1e]/80 backdrop-blur border border-[#2c2e33] text-[#e5e7eb] hover:bg-[#228be6] hover:border-[#228be6] disabled:opacity-25 disabled:pointer-events-none flex items-center justify-center shadow-lg transition-all"
        onclick={onnext}
        disabled={activeIdx >= images.length - 1}
        aria-label="Next image"
      >
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
      </button>
      <div class="absolute bottom-2 right-2 text-[11px] text-[#e5e7eb] bg-[#1a1b1e]/80 backdrop-blur px-2.5 py-1 rounded-full border border-[#2c2e33]">{activeIdx + 1} / {images.length}</div>
    {/if}
  </div>
{:else}
  <div class="h-[420px] flex items-center justify-center text-[#5c5f66] text-sm border border-[#2c2e33] rounded-xl">No preview images</div>
{/if}
