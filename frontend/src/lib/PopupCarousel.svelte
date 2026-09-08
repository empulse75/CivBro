<script lang="ts">
  import { imgSrc } from "./paths.ts";
  import { lazyVideo, hscroll } from "./actions.ts";

  interface Props {
    images: Array<{ url: string; type?: string }>;
    activeIdx: number;
    onselect: (index: number) => void;
  }

  let { images, activeIdx, onselect }: Props = $props();

  let carouselEl = $state<HTMLDivElement | null>(null);

  // Keep active thumbnail visible
  $effect(() => {
    const el = carouselEl;
    if (!el) return;
    const btn = el.querySelectorAll("button")[activeIdx] as HTMLElement | undefined;
    if (!btn) return;
    const target = btn.offsetLeft - (el.clientWidth - btn.clientWidth) / 2;
    el.scrollTo({ left: Math.max(0, Math.min(target, el.scrollWidth - el.clientWidth)), behavior: "smooth" });
  });
</script>

{#if images.length > 1}
  <div class="border-t border-[var(--civ-border,rgba(42,58,78,0.6))] bg-[var(--civ-panel,#131c29)]/60 backdrop-blur-md" data-testid="carousel">
    <div bind:this={carouselEl} use:hscroll class="flex gap-2.5 overflow-x-auto px-5 py-3 civ-hscroll">
      {#each images as img, i (img.url)}
        <button
          class="shrink-0 w-16 h-20 rounded-xl overflow-hidden border-2 transition-all duration-200 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--civ-accent,#67e8c6)]
            {i === activeIdx ? 'border-[var(--civ-accent,#67e8c6)] opacity-100 scale-105 shadow-[0_0_12px_rgba(103,232,198,0.4)]' : 'border-transparent opacity-50 hover:opacity-90 hover:scale-100'}"
          onclick={() => onselect(i)}
          title="Image {i + 1}"
          aria-label={`Select thumbnail ${i + 1}`}
        >
          {#if img.type === "video"}
            <video use:lazyVideo={img.url} muted playsinline loop preload="none" class="w-full h-full object-cover"></video>
          {:else}
            <img alt="" class="w-full h-full object-cover" decoding="async" src={imgSrc(img, 128)} loading="lazy" />
          {/if}
        </button>
      {/each}
    </div>
  </div>
{/if}
