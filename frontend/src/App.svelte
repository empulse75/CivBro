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

<svelte:window onkeydown={(event) => {
  if (event.key === "Escape" && appState.popupLoading) handleClosePopup();
}} />

<div class="studio-shell">
  {#if !compact}
    <div class="desktop-rail"><Sidebar onSelectModel={handleSelectModel} /></div>
  {/if}

  <main class="workspace">
    <header class="workspace-header">
      <div class="workspace-label"><span class="workspace-dot"></span><span>YOUR CREATIVE CORNER</span></div>
      <nav class="view-switch" aria-label="Workspace views">
        <button class:active={browse} aria-current={browse ? "page" : undefined} onclick={() => handleTabChange("browse")}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m12 3 2.7 6.3L21 12l-6.3 2.7L12 21l-2.7-6.3L3 12l6.3-2.7Z" /></svg>
          Discover
        </button>
        <button class:active={!browse} aria-current={!browse ? "page" : undefined} onclick={() => handleTabChange("local")}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M4 6h6l2 2h8v12H4Z"/><path d="M4 6V4h6l2 2h8v2"/></svg>
          My collection
        </button>
      </nav>
      {#if compact}
        <button class="civ-button filter-trigger" aria-haspopup="dialog" onclick={() => filtersOpen = true}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3" fill="currentColor"/><circle cx="15" cy="17" r="3" fill="currentColor"/></svg>
          Filters
        </button>
      {/if}
    </header>

    <section class="studio-intro" aria-labelledby="workspace-title">
      <div class="intro-copy">
        <p class="eyebrow">{browse ? "A PLAYGROUND FOR YOUR IMAGINATION" : "THE KEEPERS. THE FAVOURITES. THE WHAT-IFS."}</p>
        <h1 id="workspace-title">{browse ? "Find your next" : "Good finds."} <span>{browse ? "happy accident." : "All yours."}</span></h1>
        <p class="intro-description">{browse ? "Fresh inspiration, remarkable models. Make something a little unexpected." : "Your local model library, ready for whatever you dream up next."}</p>
      </div>
      <div class="studio-doodle" aria-hidden="true">
        <svg viewBox="0 0 210 130" fill="none">
          <ellipse cx="103" cy="67" rx="89" ry="31" transform="rotate(-22 103 67)" stroke="#67e8c6" stroke-opacity=".3" stroke-dasharray="3 5" />
          <rect x="68" y="28" width="66" height="78" rx="17" transform="rotate(-15 68 28)" fill="#1a3031" stroke="#67e8c6" stroke-opacity=".45" />
          <rect x="97" y="21" width="66" height="78" rx="17" transform="rotate(13 97 21)" fill="#27263e" stroke="#b7a4ff" stroke-opacity=".65" />
          <path d="m121 39 5 17 17 5-17 5-5 17-5-17-17-5 17-5Z" fill="#b7a4ff" />
          <circle cx="42" cy="55" r="8" fill="#67e8c6" /><path d="m173 88 3 9 9 3-9 3-3 9-3-9-9-3 9-3Z" fill="#ffc982" />
          <path d="m48 110 3-6 3 6m-3-6v13M174 27l7-6m-8 1 9 5" stroke="#ffc982" stroke-width="2" stroke-linecap="round" />
        </svg>
        <span>Stay curious.</span>
      </div>
    </section>

    {#if appState.error}
      <div class="error-notice" role="alert">
        <span>{appState.error}</span>
        <button class="civ-button" onclick={() => browse ? appState.fetchModels(true) : appState.refreshLocalModels()}>Try again</button>
      </div>
    {/if}

    {#if browse}
      <div class="collection-heading">
        <div><h2>The discovery feed</h2><span class="result-count">{appState.visibleModels.length} loaded</span></div>
        <span class="feed-note">Handmade by the community. Discovered by you.</span>
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
  .workspace-header { min-height: 72px; padding: 14px 30px; display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-shrink: 0; border-bottom: 1px solid #ffffff08; }
  .workspace-label { display: flex; align-items: center; gap: 9px; font-size: 9px; letter-spacing: 1.8px; font-weight: 700; color: var(--civ-muted); }
  .workspace-dot { width: 7px; height: 7px; background: var(--civ-accent); border-radius: 50%; box-shadow: 0 0 16px #67e8c640; }
  .view-switch { display: flex; gap: 3px; padding: 4px; border: 1px solid var(--civ-border); background: #101823; border-radius: 14px; }
  .view-switch button { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 9px 15px; color: var(--civ-muted); border-radius: 10px; font-size: 12px; font-weight: 600; transition: background .2s, color .2s; }
  .view-switch button:hover { color: var(--civ-ink); background: #1a2636; }
  .view-switch button.active { color: var(--civ-accent); background: #223b38; box-shadow: 0 2px 6px #0002; }
  .view-switch svg { width: 16px; height: 16px; }
  .studio-intro { position: relative; display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 28px 32px 25px; flex-shrink: 0; }
  .eyebrow { color: var(--civ-muted); font-size: 9px; font-weight: 650; letter-spacing: 1.9px; margin-bottom: 10px; }
  h1 { max-width: 640px; font-size: clamp(27px, 3.1vw, 44px); line-height: 1.13; font-weight: 650; letter-spacing: -1.6px; }
  h1 span { color: var(--civ-accent); }
  .intro-description { font-size: 12px; line-height: 1.7; color: var(--civ-muted); margin-top: 12px; max-width: 490px; }
  .studio-doodle { width: 180px; flex-shrink: 0; text-align: center; transform: rotate(-4deg); }
  .studio-doodle svg { width: 100%; height: 105px; }
  .studio-doodle span { color: var(--civ-warm); font-size: 11px; font-family: Georgia, serif; font-style: italic; }
  .collection-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin: 0 30px; padding: 16px 0; border-top: 1px solid var(--civ-border); flex-shrink: 0; }
  .collection-heading > div { display: flex; align-items: center; gap: 10px; }
  h2 { font-size: 13px; font-weight: 650; }
  .result-count { color: var(--civ-violet); background: #b7a4ff12; border: 1px solid #b7a4ff23; border-radius: 7px; padding: 3px 7px; font-size: 10px; font-variant-numeric: tabular-nums; }
  .feed-note { color: var(--civ-muted); font-size: 10px; }
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
  @media (max-width: 1100px) { .workspace-label { display: none; } .workspace-header { justify-content: flex-end; } .studio-doodle { width: 125px; } .feed-note { display: none; } }
  @media (max-width: 900px) { .workspace-header { justify-content: space-between; padding: 12px 20px; } .studio-intro { padding: 24px; } .collection-heading { margin: 0 24px; } }
  @media (max-width: 600px) {
    .workspace-header { padding: 10px 14px; min-height: 64px; gap: 8px; }
    .view-switch button { font-size: 11px; padding: 8px 10px; gap: 5px; }
    .view-switch svg { width: 14px; height: 14px; }
    .filter-trigger { min-height: 38px; padding: 8px 10px; font-size: 11px; }
    .studio-intro { padding: 19px 18px 20px; }
    .eyebrow { font-size: 8px; letter-spacing: 1.4px; }
    h1 { font-size: 30px; letter-spacing: -1px; max-width: 330px; }
    .intro-description { font-size: 11px; margin-top: 9px; }
    .studio-doodle { display: none; }
    .collection-heading { margin: 0 18px; padding: 12px 0; }
    .error-notice { margin: 0 14px 10px; flex-wrap: wrap; }
  }
  @media (max-height: 620px) { .studio-intro { padding-top: 14px; padding-bottom: 14px; } .studio-doodle, .intro-description, .eyebrow { display: none; } h1 { font-size: 26px; } }
</style>
