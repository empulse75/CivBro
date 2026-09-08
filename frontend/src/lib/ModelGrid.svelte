<script lang="ts">
  import ModelCard from "./ModelCard.svelte";
  import type { CivitaiModel, LocalModel } from "./stores/types";

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

<div class="discovery-scroll" bind:this={scrollContainerEl} aria-busy={loading || loadingMore}>
  {#if loading}
    <div class="loading-track" role="status" aria-label="Finding models"><div></div></div>
  {/if}

  {#if models.length > 0}
    <div class="discovery-grid">
      {#each models as model (model.id)}
        <ModelCard model={model} onSelect={() => onSelectModel(model)} />
      {/each}
    </div>
  {:else if loading}
    <div class="discovery-grid" aria-hidden="true">
      {#each Array(8) as _}
        <div class="skeleton-card">
          <div class="skeleton skeleton-art"></div>
          <div class="skeleton-copy"><div class="skeleton"></div><div class="skeleton"></div></div>
        </div>
      {/each}
    </div>
  {:else}
    <div class="empty-discovery" role="status">
      <div class="empty-art" aria-hidden="true">
        <svg viewBox="0 0 100 100" fill="none"><circle cx="44" cy="43" r="24" stroke="currentColor" stroke-width="2"/><path d="m63 62 20 20M32 43h24M44 31v24" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="m78 14 3 8 8 3-8 3-3 8-3-8-8-3 8-3Z" fill="#ffc982"/></svg>
      </div>
      <span class="empty-eyebrow">A LITTLE ROOM FOR POSSIBILITY</span>
      <h3>{local ? "Your collection starts here." : "Nothing through this lens. Yet."}</h3>
      <p>{local ? "Scan your models directory to discover what is already yours." : "Try another search or loosen a filter. Your next great find is out there."}</p>
    </div>
  {/if}

  {#if hasMore && !loading}
    <div bind:this={sentinelEl} class="feed-continuation">
      <button class="civ-button" onclick={onLoadMore} disabled={loadingMore}>
        {#if loadingMore}<span class="continuation-spinner" aria-hidden="true"></span>{/if}
        {loadingMore ? "Finding more good stuff…" : "More to explore"}
      </button>
    </div>
  {:else if models.length > 0 && !loading}
    <div class="feed-end"><span aria-hidden="true">✦</span> You’re all caught up. Go make something.</div>
  {/if}
  {#if models.length > 0}
    <!-- Overscroll room: keeps the last row from sitting on the viewport edge
         and lets new pages stream in without the scroll position jumping. -->
    <div class="feed-overscroll" aria-hidden="true"></div>
  {/if}
</div>

<style>
  .discovery-scroll { height: 100%; overflow-y: auto; overscroll-behavior: contain; padding: 10px 30px 24px; }
  .discovery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 250px), 1fr)); gap: 24px 20px; align-items: start; }
  .loading-track { position: absolute; top: 0; left: 30px; right: 30px; height: 2px; z-index: 10; overflow: hidden; background: #67e8c61a; border-radius: 4px; }
  .loading-track > div { width: 40%; height: 100%; background: var(--civ-accent); animation: loading-bar 1.5s ease-in-out infinite; }
  @keyframes loading-bar { from { transform: translateX(-100%); } to { transform: translateX(350%); } }
  .skeleton-card { border: 1px solid var(--civ-border); border-radius: 20px; overflow: hidden; background: var(--civ-panel); }
  .skeleton-art { aspect-ratio: 3 / 3.4; border-radius: 0; }
  .skeleton-copy { display: grid; gap: 9px; padding: 18px; }
  .skeleton-copy > div { height: 10px; width: 75%; }
  .skeleton-copy > div:last-child { width: 45%; }
  .empty-discovery { min-height: min(380px, 100%); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; text-align: center; padding: 28px 12px; }
  .feed-overscroll { height: 50vh; }
  .empty-art { width: 92px; height: 92px; padding: 8px; margin-bottom: 8px; color: var(--civ-accent); border-radius: 28px; background: #67e8c609; transform: rotate(-8deg); }
  .empty-eyebrow { font-size: 8px; letter-spacing: 1.8px; color: var(--civ-violet); }
  .empty-discovery h3 { font-size: clamp(20px, 2vw, 26px); letter-spacing: -.5px; font-weight: 600; }
  .empty-discovery p { max-width: 310px; color: var(--civ-muted); font-size: 12px; line-height: 1.8; }
  .feed-continuation { display: flex; justify-content: center; padding: 32px 0; }
  .continuation-spinner { width: 14px; height: 14px; border: 2px solid #67e8c62a; border-top-color: var(--civ-accent); border-radius: 50%; animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .feed-end { display: flex; justify-content: center; align-items: center; gap: 10px; padding: 32px 12px 8px; font-size: 11px; color: var(--civ-muted); text-align: center; }
  .feed-end span { color: var(--civ-warm); font-size: 18px; }
  @media (max-width: 900px) { .discovery-scroll { padding-inline: 24px; } }
  @media (max-width: 600px) { .discovery-scroll { padding: 10px 18px 18px; } .discovery-grid { gap: 20px; } .loading-track { left: 18px; right: 18px; } }
</style>
