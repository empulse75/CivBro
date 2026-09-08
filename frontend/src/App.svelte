<script lang="ts">
  import { appState } from "./lib/stores.svelte.ts";
  import Sidebar from "./lib/Sidebar.svelte";
  import ModelGrid from "./lib/ModelGrid.svelte";
  import ModelPopup from "./lib/ModelPopup.svelte";
  import LocalTab from "./lib/LocalTab.svelte";
  import type { CivitaiModel } from "./lib/stores/types";

  appState.loadSettings();

  let compact = $state(window.matchMedia("(max-width: 900px)").matches);
  let filtersOpen = $state(false);
  let filterDialog = $state<HTMLDialogElement | null>(null);
  let initialLoadDone = $state(false);
  const browse = $derived(appState.activeTab === "browse");

  $effect(() => {
    const media = window.matchMedia("(max-width: 900px)");
    const handleResize = () => { compact = media.matches; if (!compact) filtersOpen = false; };
    const handleUnload = () => appState.cleanup();
    media.addEventListener("change", handleResize);
    window.addEventListener("beforeunload", handleUnload);
    return () => {
      media.removeEventListener("change", handleResize);
      window.removeEventListener("beforeunload", handleUnload);
      appState.cleanup();
    };
  });

  $effect(() => {
    if (!filterDialog) return;
    if (filtersOpen && !filterDialog.open) filterDialog.showModal();
    else if (!filtersOpen && filterDialog.open) filterDialog.close();
  });

  $effect(() => {
    if (appState.settingsLoaded && !initialLoadDone) {
      initialLoadDone = true;
      if (browse) appState.fetchModels(true);
      else appState.refreshLocalModels();
    }
  });

  function handleSelectModel(model: CivitaiModel) {
    filtersOpen = false;
    filterDialog?.close();
    appState.openModelDetail(model);
  }

  function handleClosePopup() { appState.closeModelDetail(); }

  function handleTabChange(tab: "browse" | "local") {
    if (appState.activeTab === tab) return;
    appState.activeTab = tab;
    if (tab === "browse") appState.fetchModels(true);
    else appState.refreshLocalModels();
  }
</script>
  <div class="studio-shell">
    {#if !compact}
      <div class="desktop-rail"><Sidebar onSelectModel={handleSelectModel} /></div>
    {/if}

    <main class="workspace">
      {#if compact}
        <header class="workspace-header">
          <button class="civ-button filter-trigger" aria-haspopup="dialog" onclick={() => filtersOpen = true}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3" fill="currentColor"/><circle cx="15" cy="17" r="3" fill="currentColor"/></svg>
            Filters
          </button>
        </header>
      {/if}

      {#if appState.error}
        <div class="error-notice" role="alert">
          <span>{appState.error}</span>
          <button class="civ-button" onclick={() => browse ? appState.fetchModels(true) : appState.refreshLocalModels()}>Try again</button>
        </div>
      {/if}

      <div class="workspace-content">
        {#if browse}
          <ModelGrid models={appState.visibleModels} loading={appState.isLoading} loadingMore={appState.isLoadingMore} hasMore={appState.hasMore} onSelectModel={handleSelectModel} onLoadMore={() => appState.loadMore()} />
        {:else}
          <LocalTab />
        {/if}
      </div>
    </main>
  </div>

{#if compact}
  <dialog class="filter-dialog" bind:this={filterDialog} aria-label="Browse filters and settings" onclose={() => filtersOpen = false} oncancel={() => filtersOpen = false}>
    <div class="drawer-heading"><span>MAKE IT YOUR KIND OF WEIRD</span><button class="civ-button civ-icon-button" aria-label="Close filters" onclick={() => filtersOpen = false}>×</button></div>
    <div class="drawer-content"><Sidebar onSelectModel={handleSelectModel} /></div>
    <div class="drawer-footer"><button class="civ-button primary" onclick={() => filtersOpen = false}>Back to the good stuff <span aria-hidden="true">↗</span></button></div>
  </dialog>
{/if}

{#if appState.selectedModel}
  <ModelPopup model={appState.selectedModel} versions={appState.modelVersions} selectedVersion={appState.selectedVersion} installedVersionIds={appState.installedVersionIds} onClose={handleClosePopup} onSelectVersion={(version) => appState.selectVersion(version)} />
{:else if appState.popupLoading}
  <div class="detail-loading backdrop-in">
    <div class="loading-panel popup-enter" role="status">
      <span class="loading-orbit" aria-hidden="true"></span>
      <h2>A closer look…</h2><p>Bringing the details into focus.</p>
      <button class="civ-button" onclick={handleClosePopup}>Cancel</button>
    </div>
  </div>
{/if}

<style>
  .studio-shell { display: flex; height: 100%; background: var(--civ-bg); }
  .desktop-rail { width: 280px; flex-shrink: 0; min-height: 0; border-right: 1px solid var(--civ-border); }
  .workspace { display: flex; flex-direction: column; flex: 1; min-width: 0; min-height: 0; background: radial-gradient(ellipse at 70% 0, #14242b 0, transparent 55%); }
  .workspace-header { padding: 10px 30px 6px; display: flex; justify-content: flex-end; flex-shrink: 0; }
  .workspace-content { flex: 1; min-height: 0; overflow: hidden; position: relative; }
  .error-notice { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin: 0 30px 12px; padding: 12px 16px; border: 1px solid #ff99844d; border-radius: 14px; background: #ff998410; color: #ffc1b4; font-size: 12px; }
  .error-notice span { overflow-wrap: anywhere; }
  .filter-dialog { position: fixed; inset: 0 auto 0 0; margin: 0; width: min(360px, calc(100vw - 20px)); max-width: none; height: 100%; height: 100dvh; max-height: none; padding: 0; border: 0; border-right: 1px solid var(--civ-border); background: var(--civ-bg); color: var(--civ-ink); }
  .filter-dialog[open] { display: flex; flex-direction: column; }
  .filter-dialog::backdrop { background: #040911bf; backdrop-filter: blur(5px); }
  .drawer-heading { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; gap: 12px; border-bottom: 1px solid var(--civ-border); }
  .drawer-heading > span { font-size: 9px; color: var(--civ-muted); letter-spacing: 1px; }
  .drawer-content { flex: 1; min-height: 0; overflow: hidden; }
  .drawer-footer { padding: 12px 16px max(12px, env(safe-area-inset-bottom)); border-top: 1px solid var(--civ-border); }
  .drawer-footer button { width: 100%; }
  .detail-loading { position: fixed; inset: 0; z-index: 50; display: grid; place-items: center; background: #040911ce; backdrop-filter: blur(8px); }
  .loading-panel { text-align: center; display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 32px; border: 1px solid var(--civ-border); border-radius: 24px; background: var(--civ-panel); }
  .loading-panel h2 { font-size: 20px; }
  .loading-panel p { color: var(--civ-muted); font-size: 12px; }
  .loading-orbit { width: 40px; height: 40px; margin-bottom: 8px; border: 2px solid #67e8c625; border-top-color: var(--civ-accent); border-radius: 50%; animation: orbit 1s linear infinite; }
  @keyframes orbit { to { transform: rotate(360deg); } }
  @media (max-width: 900px) { .workspace-header { padding: 10px 20px 6px; } }
  @media (max-width: 600px) {
    .workspace-header { padding: 10px 14px 4px; }
    .filter-trigger { min-height: 38px; padding: 8px 10px; font-size: 11px; }
    .error-notice { margin: 0 14px 10px; flex-wrap: wrap; }
  }
</style>
