<script lang="ts">
  import { appState } from "./lib/stores.svelte.ts";
  import Sidebar from "./lib/Sidebar.svelte";
  import ModelGrid from "./lib/ModelGrid.svelte";
  import ModelPopup from "./lib/ModelPopup.svelte";
  import LocalTab from "./lib/LocalTab.svelte";
  import type { CivitaiModel } from "./lib/stores/types";

  appState.loadSettings();

  $effect(() => {
    const handleUnload = () => appState.cleanup();
    window.addEventListener("beforeunload", handleUnload);
    return () => {
      window.removeEventListener("beforeunload", handleUnload);
      appState.cleanup();
    };
  });

  let initialLoadDone = $state(false);

  $effect(() => {
    if (appState.settingsLoaded && !initialLoadDone) {
      initialLoadDone = true;
      if (appState.activeTab === "browse") {
        appState.fetchModels(true);
      } else if (appState.activeTab === "local") {
        appState.refreshLocalModels();
      }
    }
  });

  function handleSelectModel(model: CivitaiModel) {
    appState.openModelDetail(model);
  }

  function handleClosePopup() {
    appState.closeModelDetail();
  }

  function handleTabChange(tab: "browse" | "local") {
    appState.activeTab = tab;
    if (tab === "browse") appState.fetchModels(true);
    else appState.refreshLocalModels();
  }
</script>

<div class="flex h-full bg-[#0f1117]">
  <Sidebar onSelectModel={handleSelectModel} />

  <main class="flex-1 overflow-hidden flex flex-col min-w-0 pl-0.5">
    <div class="flex items-center gap-1 px-4 pt-3 pb-0 border-b border-[#1a1b1e] shrink-0">
      <button
        class="px-4 py-2 text-sm rounded-t-lg transition-colors duration-200
          {appState.activeTab === 'browse'
            ? 'bg-[#1a1b1e] text-white border-b-2 border-[#2563eb]'
            : 'text-gray-400 hover:text-white hover:bg-[#1a1b1e]'}"
        onclick={() => handleTabChange("browse")}
      >
        Browse
      </button>
      <button
        class="px-4 py-2 text-sm rounded-t-lg transition-colors duration-200
          {appState.activeTab === 'local'
            ? 'bg-[#1a1b1e] text-white border-b-2 border-[#2563eb]'
            : 'text-gray-400 hover:text-white hover:bg-[#1a1b1e]'}"
        onclick={() => handleTabChange("local")}
      >
        Local
      </button>
    </div>

    {#if appState.error}
      <div class="m-4 p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
        {appState.error}
        <button class="ml-3 underline hover:text-red-200" onclick={() => appState.fetchModels(true)}>
          Retry
        </button>
      </div>
    {/if}

    <div class="flex-1 overflow-hidden relative">
      {#if appState.activeTab === "browse"}
        <ModelGrid
          models={appState.visibleModels}
          loading={appState.isLoading}
          loadingMore={appState.isLoadingMore}
          hasMore={appState.hasMore}
          onSelectModel={handleSelectModel}
          onLoadMore={() => appState.loadMore()}
        />
      {:else}
        <LocalTab />
      {/if}
    </div>
  </main>
</div>

{#if appState.selectedModel}
  <ModelPopup
    model={appState.selectedModel}
    versions={appState.modelVersions}
    selectedVersion={appState.selectedVersion}
    installedVersionIds={appState.installedVersionIds}
    onClose={handleClosePopup}
    onSelectVersion={(v) => appState.selectVersion(v)}
  />
{:else if appState.popupLoading}
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm backdrop-in"
    onclick={handleClosePopup}
    onkeydown={(e) => { if (e.key === 'Escape') handleClosePopup(); }}
    role="button"
    tabindex="0"
    aria-label="Loading model details"
  >
    <div class="flex flex-col items-center gap-4 pointer-events-none popup-enter">
      <div class="relative">
        <div class="w-12 h-12 rounded-full border-[3px] border-[#2563eb]/30"></div>
        <div class="w-12 h-12 rounded-full border-[3px] border-[#2563eb] border-t-transparent absolute inset-0 animate-spin"></div>
      </div>
      <span class="text-gray-300 text-sm font-medium">Loading model details…</span>
      <div class="flex gap-1.5">
        <div class="w-2 h-2 rounded-full bg-[#2563eb] skeleton" style="animation-delay:0s"></div>
        <div class="w-2 h-2 rounded-full bg-[#2563eb] skeleton" style="animation-delay:0.15s"></div>
        <div class="w-2 h-2 rounded-full bg-[#2563eb] skeleton" style="animation-delay:0.3s"></div>
      </div>
    </div>
  </div>
{/if}
