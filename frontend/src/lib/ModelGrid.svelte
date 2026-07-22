<script lang="ts">
  import ModelCard from "./ModelCard.svelte";
  import type { CivitaiModel, LocalModel } from "./stores.svelte.ts";

  interface Props {
    models: CivitaiModel[];
    localModels?: LocalModel[];
    loading: boolean;
    loadingMore: boolean;
    hasMore: boolean;
    onSelectModel: (model: CivitaiModel) => void;
    onLoadMore: () => void;
    local?: boolean;
  }

  let {
    models,
    localModels = [],
    loading,
    loadingMore,
    hasMore,
    onSelectModel,
    onLoadMore,
    local = false,
  }: Props = $props();

  let sentinelEl = $state<HTMLDivElement | null>(null);
  let scrollContainerEl = $state<HTMLDivElement | null>(null);

  $effect(() => {
    if (!sentinelEl) return;

    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loading && !loadingMore) {
          onLoadMore();
        }
      },
      { root: scrollContainerEl, rootMargin: "400px" }
    );

    obs.observe(sentinelEl);

    return () => obs.disconnect();
  });
</script>

<div class="h-full overflow-y-auto p-4" bind:this={scrollContainerEl}>
  {#if loading}
    <div class="absolute top-0 left-0 right-0 h-0.5 bg-[#1a1b1e] z-10">
      <div class="h-full bg-[#2563eb] animate-loading-bar"></div>
    </div>
  {/if}

  {#if models.length > 0}
    <div
      class="grid gap-3 md:gap-4"
      style="grid-template-columns: repeat(auto-fill, minmax(285px, 1fr));"
    >
      {#each models as model (model.id)}
        <ModelCard model={model} onSelect={() => onSelectModel(model)} />
      {/each}
    </div>

    {#if loadingMore}
      <div class="flex justify-center py-6">
        <div class="w-6 h-6 border-2 border-[#2563eb] border-t-transparent rounded-full animate-spin"></div>
      </div>
    {/if}
  {:else if loading}
    <div
      class="grid gap-3 md:gap-4"
      style="grid-template-columns: repeat(auto-fill, minmax(285px, 1fr));"
    >
      {#each Array(12) as _}
        <div class="rounded-xl overflow-hidden bg-[#1a1b1e] animate-pulse">
          <div class="aspect-[3/4] bg-[#2a2b30]"></div>
        </div>
      {/each}
    </div>
  {:else}
    <div class="flex flex-col items-center justify-center h-full text-center py-20">
      <div class="text-gray-500 text-5xl mb-4">
        {local ? "No local models" : "No results found"}
      </div>
      <p class="text-gray-400 text-sm">
        {local
          ? "Scan your models directory to populate this view."
          : "Try adjusting your filters or search query."}
      </p>
    </div>
  {/if}

  {#if hasMore && !loading}
    <div bind:this={sentinelEl} class="h-4"></div>
    <!-- Overscroll room: lets you scroll ~half a page past the last row so the
         next page can stream in underneath while you keep scrolling (smoother
         than hitting a hard stop). Collapses once everything is loaded. -->
    <div class="w-full" style="height:50vh" aria-hidden="true"></div>
  {/if}

  {#if !hasMore && models.length > 0}
    <div class="text-center py-6 text-xs text-gray-600">
      All models loaded
    </div>
  {/if}
</div>

<style>
  @keyframes loading-bar {
    0% { width: 0%; margin-left: 0%; }
    50% { width: 60%; margin-left: 20%; }
    100% { width: 0%; margin-left: 100%; }
  }
  .animate-loading-bar {
    animation: loading-bar 1.5s ease-in-out infinite;
  }
</style>
