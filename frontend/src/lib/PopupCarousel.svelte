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
  <div class="border-t border-[#2c2e33] bg-[#161719]" data-testid="carousel">
    <div bind:this={carouselEl} use:hscroll class="flex gap-2 overflow-x-auto px-5 py-3 civ-hscroll">
      {#each images as img, i (img.url)}
        <button
          class="shrink-0 w-16 h-20 rounded-lg overflow-hidden border-2 transition-all
            {i === activeIdx ? 'border-[#228be6] opacity-100' : 'border-transparent opacity-45 hover:opacity-80'}"
          onclick={() => onselect(i)}
          title="Image {i + 1}"
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
