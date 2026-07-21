<script lang="ts">
  import { scanLocalModels, deleteLocalModel } from "./api";
  import { appState } from "./stores.svelte.ts";

  let searchQuery = $state("");
  let scanning = $state(false);

  // $derived.by (not $derived(fn)) — $derived(() => ...) would store the arrow
  // function itself, so `.length`/iteration would operate on a function. Read
  // appState.localModels directly so the value stays reactive (destructuring a
  // rune-backed getter would snapshot it and lose reactivity).
  let filteredModels = $derived.by(() => {
    const models = appState.localModels;
    if (!searchQuery.trim()) return models;
    const q = searchQuery.toLowerCase();
    return models.filter(
      (m) =>
        m.name.toLowerCase().includes(q) ||
        m.path.toLowerCase().includes(q) ||
        m.type.toLowerCase().includes(q)
    );
  });

  async function handleScan() {
    scanning = true;
    try {
      await scanLocalModels();
      await appState.refreshLocalModels();
    } catch (e) {
      appState.error = e instanceof Error ? e.message : "Scan failed";
    } finally {
      scanning = false;
    }
  }

  async function handleRemove(modelId: number | undefined) {
    if (!modelId) return;
    try {
      await deleteLocalModel(modelId);
      await appState.refreshLocalModels();
    } catch (e) {
      appState.error = e instanceof Error ? e.message : "Failed to remove";
    }
  }

  function formatSize(bytes: number): string {
    if (bytes >= 1000000000) return (bytes / 1000000000).toFixed(1) + " GB";
    if (bytes >= 1000000) return (bytes / 1000000).toFixed(1) + " MB";
    if (bytes >= 1000) return (bytes / 1000).toFixed(0) + " KB";
    return bytes + " B";
  }

  function formatPath(path: string): string {
    const parts = path.split(/[\\/]/);
    return parts.slice(-2).join("/");
  }
</script>

<div class="h-full flex flex-col">
  <div class="flex items-center gap-3 px-4 py-3 border-b border-[#1a1b1e] shrink-0">
    <input
      type="text"
      placeholder="Filter local models..."
      class="flex-1 px-3 py-2 text-sm bg-[#1a1b1e] border border-[#2a2b30] rounded-lg text-white
        placeholder-gray-500 outline-none focus:border-[#2563eb] transition-colors duration-200"
      bind:value={searchQuery}
    />
    <button
      class="px-4 py-2 rounded-lg text-sm font-medium text-white bg-[#2563eb]
        hover:bg-[#1d4ed8] transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
      onclick={handleScan}
      disabled={scanning}
    >
      {scanning ? "Scanning..." : "Scan Models"}
    </button>
    <button
      class="px-4 py-2 rounded-lg text-sm font-medium text-gray-300 bg-[#2a2b30]
        hover:bg-[#3a3b40] hover:text-white transition-colors duration-200 whitespace-nowrap"
      onclick={() => appState.refreshLocalModels()}
    >
      Refresh
    </button>
  </div>

  <div class="flex-1 overflow-y-auto p-4">
    {#if filteredModels.length === 0}
      <div class="flex flex-col items-center justify-center h-full text-center py-20">
        <div class="text-gray-500 text-4xl mb-4">No local models</div>
        <p class="text-gray-400 text-sm mb-4">
          {searchQuery.trim()
            ? "No models match your search."
            : "Click Scan to discover models in your directories."}
        </p>
      </div>
    {:else}
      <div class="space-y-2">
        {#each filteredModels as m}
          <div class="flex items-center gap-4 p-3 bg-[#1a1b1e] rounded-xl hover:bg-[#202125] transition-colors duration-150">
            <div class="flex-1 min-w-0">
              <p class="text-sm font-medium text-white truncate">{m.name}</p>
              <div class="flex items-center gap-2 mt-1">
                <span class="text-[10px] text-gray-500 bg-[#2a2b30] rounded-full px-2 py-0.5">
                  {m.type}
                </span>
                <span class="text-[10px] text-gray-500">{formatSize(m.size)}</span>
                <span class="text-[10px] text-gray-500 truncate hidden sm:inline">
                  {formatPath(m.path)}
                </span>
              </div>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              {#if m.modelId}
                <button
                  class="px-3 py-1 rounded-full text-xs text-[#60a5fa] bg-[#2563eb]/10
                    hover:bg-[#2563eb]/20 transition-colors duration-150"
                  onclick={() => {
                    appState.activeTab = "browse";
                    appState.openModelDetail({
                      id: m.modelId!,
                      name: m.name,
                      type: m.type,
                      nsfw: false,
                    });
                  }}
                >
                  View
                </button>
              {/if}
              <button
                class="px-3 py-1 rounded-full text-xs text-red-400 bg-red-400/10
                  hover:bg-red-400/20 transition-colors duration-150"
                onclick={() => handleRemove(m.modelId)}
              >
                Remove
              </button>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</div>
