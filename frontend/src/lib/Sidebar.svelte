<script lang="ts">
  import { appState } from "./stores.svelte.ts";
  import type { CivitaiModel } from "./stores.svelte.ts";

  interface Props {
    onSelectModel?: (model: CivitaiModel) => void;
  }

  let { onSelectModel }: Props = $props();

  let searchInput = $state("");
  let searchFocused = $state(false);
  let debounceTimer: ReturnType<typeof setTimeout>;
  let fuzzyTimer: ReturnType<typeof setTimeout>;
  let apiKeyInput = $state("");
  let apiKeyValidationStatus = $state<"valid" | "invalid" | "checking" | null>(null);
  let keyDebounceTimer: ReturnType<typeof setTimeout>;
  let dragIdx = $state<number | null>(null);

  const categories = [
    { value: "", label: "All" },
    { value: "Checkpoint", label: "Checkpoint" },
    { value: "LORA", label: "LORA" },
    { value: "TextualInversion", label: "Embedding" },
    { value: "VAE", label: "VAE" },
    { value: "Controlnet", label: "ControlNet" },
    { value: "Upscaler", label: "Upscaler" },
    { value: "MotionModule", label: "Motion" },
    { value: "AestheticGradient", label: "Aesthetic" },
    { value: "Poses", label: "Poses" },
    { value: "Wildcards", label: "Wildcards" },
    { value: "Other", label: "Other" },
  ];

  const baseModels = [
    { value: "", label: "All" },
    { value: "SD 1.4", label: "SD 1.4" },
    { value: "SD 1.5", label: "SD 1.5" },
    { value: "SD 2.0", label: "SD 2.0" },
    { value: "SD 2.1", label: "SD 2.1" },
    { value: "SDXL 0.9", label: "SDXL 0.9" },
    { value: "SDXL 1.0", label: "SDXL 1.0" },
    { value: "SD 3", label: "SD 3" },
    { value: "SD 3.5", label: "SD 3.5" },
    { value: "Pony", label: "Pony" },
    { value: "Illustrious", label: "Illustrious" },
    { value: "NoobAI", label: "NoobAI" },
    { value: "Flux.1 D", label: "Flux.1 D" },
    { value: "Flux.1 S", label: "Flux.1 S" },
    { value: "Flux.2 D", label: "Flux.2 D" },
    { value: "Flux.2 Klein 4B", label: "Flux.2 K4B" },
    { value: "Flux.2 Klein 9B", label: "Flux.2 K9B" },
    { value: "Flux.2 Klein 9B-base", label: "Flux.2 K9B-B" },
    { value: "Anima", label: "Anima" },
    { value: "Chroma", label: "Chroma" },
    { value: "ZImageBase", label: "ZImageBase" },
    { value: "ZImageTurbo", label: "ZImageTurbo" },
    { value: "Krea 2", label: "Krea 2" },
    { value: "Qwen", label: "Qwen" },
    { value: "Ernie", label: "Ernie" },
    { value: "AuraFlow", label: "AuraFlow" },
    { value: "Stable Cascade", label: "Cascade" },
    { value: "PixArt-a", label: "PixArt-α" },
    { value: "PixArt-E", label: "PixArt-Σ" },
    { value: "SVD", label: "SVD" },
    { value: "SVD XT", label: "SVD XT" },
    { value: "Hunyuan Video", label: "Hunyuan" },
    { value: "Wan Video 2.2 T2V-A14B", label: "Wan" },
    { value: "Mochi 1", label: "Mochi 1" },
    { value: "CogVideo", label: "CogVideo" },
    { value: "ACE Audio", label: "ACE Audio" },
    { value: "Lumina", label: "Lumina" },
    { value: "Kolors", label: "Kolors" },
    { value: "Aurora", label: "Aurora" },
    { value: "SDXS", label: "SDXS" },
    { value: "Other", label: "Other" },
  ];

  const periods = [
    { value: "AllTime", label: "All Time" },
    { value: "Week", label: "Week" },
    { value: "Month", label: "Month" },
    { value: "Year", label: "Year" },
  ];

  const sortOptions = [
    { value: "Most Downloaded", label: "Most Downloaded" },
    { value: "Highest Rated", label: "Highest Rated" },
    { value: "Most Liked", label: "Most Liked" },
    { value: "Most Discussed", label: "Most Discussed" },
    { value: "Most Collected", label: "Most Collected" },
    { value: "Newest", label: "Newest" },
  ];

  $effect(() => {
    if (appState.settingsLoaded) {
      searchInput = appState.filters.search;
      if (appState.apiKey) {
        apiKeyInput = appState.apiKey;
        apiKeyValidationStatus = appState.apiKeyValid === true ? "valid"
          : appState.apiKeyValid === false ? "invalid" : null;
      }
    }
  });

  function handleKeyChange() {
    clearTimeout(keyDebounceTimer);
    const val = apiKeyInput.trim();
    if (!val) {
      apiKeyValidationStatus = null;
      appState.validateAndSaveKey("");
      return;
    }
    apiKeyValidationStatus = "checking";
    keyDebounceTimer = setTimeout(async () => {
      await appState.validateAndSaveKey(val);
      apiKeyValidationStatus = appState.apiKeyValid === true ? "valid"
        : appState.apiKeyValid === false ? "invalid" : null;
    }, 600);
  }

  function handleSearchInput(value: string) {
    searchInput = value;
    clearTimeout(debounceTimer);
    clearTimeout(fuzzyTimer);
    debounceTimer = setTimeout(() => {
      appState.setFilter("search", value);
    }, 400);
    if (value.length >= 2) {
      fuzzyTimer = setTimeout(() => {
        appState.fetchSuggestions(value);
      }, 250);
    }
  }

  function handleSearchKeydown(e: KeyboardEvent) {
    if (e.key === "Enter") {
      clearTimeout(debounceTimer);
      appState.setFilter("search", searchInput);
      appState.triggerSearch();
    }
  }

  function handleSearchClick() {
    appState.setFilter("search", searchInput);
    appState.triggerSearch();
  }

  function handleSuggestionClick(suggestion: string) {
    searchInput = suggestion;
    appState.setFilter("search", suggestion);
    appState.suggestions.length = 0;
    appState.triggerSearch();
  }

  function handleCategorySelect(value: string) {
    appState.toggleModelType(value);
  }

  function handleBaseModelSelect(value: string) {
    appState.toggleBaseModel(value);
  }

  function chipClass(selected: boolean) {
    return selected
      ? "!bg-[#2563eb] !text-white !border-[#3b82f6]"
      : "!bg-[#25262b] !text-[#909296] hover:!bg-[#2c2e33] hover:!text-[#c1c2c5] hover:!border-[#373a40]";
  }

  function categoryChipClass(val: string) {
    return chipClass(appState.filters.modelType.includes(val));
  }

  function baseModelChipClass(val: string) {
    return chipClass(appState.filters.baseModel.includes(val));
  }

  function handlePeriodSelect(value: string) {
    appState.setFilter("period", appState.filters.period === value ? "AllTime" : value);
  }

  function handleSortSelect(value: string) {
    appState.setFilter("sort", value);
  }

  function toggleNsfw() {
    appState.setFilter("nsfw", !appState.filters.nsfw);
  }

  function toggleNsfwBlur() {
    appState.nsfwBlurEnabled = !appState.nsfwBlurEnabled;
    appState.saveSettings();
  }

  function fmtBytes(b: number) {
    if (!b) return "0";
    if (b >= 1e9) return (b / 1e9).toFixed(2) + " GB";
    if (b >= 1e6) return (b / 1e6).toFixed(1) + " MB";
    if (b >= 1e3) return (b / 1e3).toFixed(0) + " KB";
    return b + " B";
  }
  function fmtSpeed(bps: number) {
    if (!bps || bps < 1) return "";
    if (bps >= 1e9) return (bps / 1e9).toFixed(1) + " GB/s";
    if (bps >= 1e6) return (bps / 1e6).toFixed(1) + " MB/s";
    if (bps >= 1e3) return (bps / 1e3).toFixed(0) + " KB/s";
    return Math.round(bps) + " B/s";
  }
  function fmtEta(sec: number) {
    if (!sec || sec <= 0) return "";
    if (sec >= 3600) return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
    if (sec >= 60) return `${Math.floor(sec / 60)}m ${sec % 60}s`;
    return `${sec}s`;
  }
</script>

<aside class="w-[284px] shrink-0 bg-[#0f1117] border-r border-[#1a1b1e] flex flex-col h-full overflow-hidden">
  <div class="px-4 py-3.5 border-b border-[#1a1b1e]">
    <h1 class="text-lg font-bold text-white tracking-tight">CivBro</h1>
    <p class="text-[11px] text-gray-500 mt-0.5">Civitai Browser</p>
  </div>

  <div class="flex-1 overflow-y-auto pl-3 pr-6 py-3 flex flex-col gap-3">
    <!-- Search -->
    <div>
      <div class="flex gap-1.5">
        <div class="relative flex-1">
          <svg class="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none z-0" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd" />
          </svg>
          <input
            type="text"
            placeholder="Search models..."
            class="w-full pl-3 pr-9 py-2 text-sm bg-[#1a1b1e] border border-[#2a2b30] rounded-lg text-white
              placeholder-gray-500 outline-none focus:border-[#2563eb] transition-all duration-200"
            value={searchInput}
            oninput={(e) => handleSearchInput((e.target as HTMLInputElement).value)}
            onkeydown={handleSearchKeydown}
            onfocus={() => (searchFocused = true)}
            onblur={() => setTimeout(() => (searchFocused = false), 200)}
          />
        </div>
        <button
          class="px-3.5 py-2 text-sm font-medium bg-[#2563eb] hover:bg-[#1d4ed8] text-white rounded-lg
            transition-colors duration-150 shrink-0"
          onclick={handleSearchClick}
        >
          Search
        </button>
      </div>
      {#if searchFocused && appState.suggestions.length > 0 && searchInput.length >= 2}
        <div class="relative mt-1 bg-[#1a1b1e] border border-[#2a2b30] rounded-lg overflow-hidden z-10 shadow-xl">
          {#each appState.suggestions as suggestion}
            <button
              class="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-[#2a2b30] hover:text-white
                transition-colors duration-100 border-b border-[#25262b] last:border-0"
              onmousedown={() => handleSuggestionClick(suggestion)}
            >
              {suggestion}
            </button>
          {/each}
        </div>
      {/if}
    </div>

    <!-- Category (always expanded) -->
    <div>
      <h3 class="text-[12px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Model types</h3>
      <div class="flex flex-wrap gap-1.5">
        {#each categories as cat}
          <button
            style="border-radius:14px;padding:2px 10px;font-size:12px;font-weight:500;line-height:1.3;transition:all 0.15s ease;border:1px solid transparent"
            class={categoryChipClass(cat.value)}
            onclick={() => handleCategorySelect(cat.value)}
          >
            {cat.label}
          </button>
        {/each}
      </div>
    </div>

    <hr class="border-0 h-px my-1" style="background:linear-gradient(90deg, transparent, rgba(59,130,246,0.3) 20%, rgba(59,130,246,0.3) 80%, transparent)" />

    <!-- Base Model (always expanded) -->
    <div>
      <h3 class="text-[12px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Base Model</h3>
      <div class="flex flex-wrap gap-1.5">
        {#each baseModels as bm}
          <button
            style="border-radius:14px;padding:2px 10px;font-size:12px;font-weight:500;line-height:1.3;transition:all 0.15s ease;border:1px solid transparent"
            class={baseModelChipClass(bm.value)}
            onclick={() => handleBaseModelSelect(bm.value)}
          >
            {bm.label}
          </button>
        {/each}
      </div>
    </div>

    <hr class="border-0 h-px my-1" style="background:linear-gradient(90deg, transparent, rgba(59,130,246,0.3) 20%, rgba(59,130,246,0.3) 80%, transparent)" />

    <!-- Period -->
    <div>
      <h3 class="text-[12px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Period</h3>
      <div class="flex flex-wrap gap-1.5">
        {#each periods as p}
          <button
            style="border-radius:14px;padding:2px 10px;font-size:12px;font-weight:500;line-height:1.3;transition:all 0.15s ease;border:1px solid transparent"
            class={chipClass(appState.filters.period === p.value)}
            onclick={() => handlePeriodSelect(p.value)}
          >
            {p.label}
          </button>
        {/each}
      </div>
    </div>

    <hr class="border-0 h-px my-1" style="background:linear-gradient(90deg, transparent, rgba(59,130,246,0.3) 20%, rgba(59,130,246,0.3) 80%, transparent)" />

    <!-- Sort -->
    <div>
      <h3 class="text-[12px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Sort</h3>
      <div class="flex flex-wrap gap-1.5">
        {#each sortOptions as s}
          <button
            style="border-radius:14px;padding:2px 10px;font-size:12px;font-weight:500;line-height:1.3;transition:all 0.15s ease;border:1px solid transparent"
            class={chipClass(appState.filters.sort === s.value)}
            onclick={() => handleSortSelect(s.value)}
          >
            {s.label}
          </button>
        {/each}
      </div>
    </div>

    <!-- NSFW toggles -->
    <div class="border-t border-[#1a1b1e] pt-3">
      <div class="flex items-center justify-between mb-2.5">
        <span class="text-[13px] text-gray-300 font-medium">Show NSFW</span>
        <button
          class="w-11 h-6 rounded-full transition-all duration-200 relative {appState.filters.nsfw ? 'bg-[#2563eb]' : 'bg-[#3a3b40]'} hover:opacity-90"
          onclick={toggleNsfw}
          role="switch"
          aria-checked={appState.filters.nsfw}
          aria-label="Toggle NSFW content"
        >
          <span class="absolute top-[3px] w-[18px] h-[18px] rounded-full bg-white shadow transition-all duration-200
            {appState.filters.nsfw ? 'left-[21px]' : 'left-[3px]'}"
          ></span>
        </button>
      </div>

      <div class="flex items-center justify-between">
        <span class="text-[13px] text-gray-300 font-medium">Blur NSFW</span>
        <button
          class="w-11 h-6 rounded-full transition-all duration-200 relative {appState.nsfwBlurEnabled ? 'bg-[#2563eb]' : 'bg-[#3a3b40]'} hover:opacity-90"
          onclick={toggleNsfwBlur}
          role="switch"
          aria-checked={appState.nsfwBlurEnabled}
          aria-label="Toggle NSFW blur"
        >
          <span class="absolute top-[3px] w-[18px] h-[18px] rounded-full bg-white shadow transition-all duration-200
            {appState.nsfwBlurEnabled ? 'left-[21px]' : 'left-[3px]'}"
          ></span>
        </button>
      </div>
    </div>

    <!-- Only Installed Toggle -->
    <div class="border-t border-[#1a1b1e] pt-3">
      <div class="flex items-center justify-between">
        <span class="text-[13px] text-gray-300 font-medium">Only Installed</span>
        <button
          class="w-11 h-6 rounded-full transition-all duration-200 relative {appState.onlyInstalled ? 'bg-[#22c55e]' : 'bg-[#3a3b40]'} hover:opacity-90"
          onclick={() => {
            appState.onlyInstalled = !appState.onlyInstalled;
            appState.triggerSearch();
          }}
          role="switch"
          aria-checked={appState.onlyInstalled}
          aria-label="Show only locally installed models"
        >
          <span class="absolute top-[3px] w-[18px] h-[18px] rounded-full bg-white shadow transition-all duration-200
            {appState.onlyInstalled ? 'left-[21px]' : 'left-[3px]'}"
          ></span>
        </button>
      </div>
    </div>

    <!-- Fast Search Toggle -->
    <div class="border-t border-[#1a1b1e] pt-3">
      <div class="flex items-center justify-between">
        <span class="text-[13px] text-gray-300 font-medium">Fast Search</span>
        <button
          class="w-11 h-6 rounded-full transition-all duration-200 relative {appState.fastSearch ? 'bg-[#2563eb]' : 'bg-[#3a3b40]'} hover:opacity-90"
          onclick={() => { appState.fastSearch = !appState.fastSearch; }}
          role="switch"
          aria-checked={appState.fastSearch}
          aria-label="Use AllTime period for search-box queries (keeps other filters intact)"
        >
          <span class="absolute top-[3px] w-[18px] h-[18px] rounded-full bg-white shadow transition-all duration-200
            {appState.fastSearch ? 'left-[21px]' : 'left-[3px]'}"
          ></span>
        </button>
      </div>
    </div>

    <!-- API Key -->
    <div class="border-t border-[#1a1b1e] pt-3">
      <div class="flex items-center gap-2">
        <span class="text-[13px] text-gray-300 font-medium">civitai.red API Key</span>
        {#if apiKeyValidationStatus === 'valid'}
          <span class="text-[10px] font-semibold uppercase tracking-wide text-[#22c55e] bg-[#1e3226] border border-[#2f9e44]/40 rounded-full px-2 py-0.5 leading-none">valid</span>
        {:else if apiKeyValidationStatus === 'invalid'}
          <span class="text-[10px] font-semibold uppercase tracking-wide text-[#ff6b6b] bg-[#2c1a1a] border border-[#e03131]/40 rounded-full px-2 py-0.5 leading-none">invalid</span>
        {/if}
      </div>
      <div class="flex items-center gap-2 mt-2">
        <input
          type="password"
          placeholder="Enter API key..."
          class="flex-1 px-3 py-1.5 text-sm bg-[#1a1b1e] border border-[#2a2b30] rounded-lg text-white
            placeholder-gray-500 outline-none focus:border-[#2563eb] transition-all duration-200"
          bind:value={apiKeyInput}
          oninput={handleKeyChange}
        />
      </div>
    </div>

    <button
      class="w-full py-2 text-[13px] text-gray-500 hover:text-white bg-[#1a1b1e] hover:bg-[#2a2b30]
        rounded-lg transition-colors duration-200 font-medium"
      onclick={() => {
        appState.clearFilters();
        searchInput = "";
      }}
    >
      Clear Filters
    </button>

    {#if appState.hasActiveDownloads}
      <div class="border-t border-[#1a1b1e] pt-3">
        <span class="text-[13px] text-gray-300 font-medium">Downloads</span>
        <div class="mt-2 flex flex-col gap-2 mr-0.5" role="list">
          {#each appState.activeDownloads as dl, i}
            {@const isRunning = dl.status === "downloading"}
            {@const isQueued = dl.status === "queued" || dl.status === "pending"}
            {@const speedStr = isRunning && dl.speed ? fmtSpeed(dl.speed) : ""}
            {@const etaStr = isRunning && dl.etaSec ? `ETA ${fmtEta(dl.etaSec)}` : ""}
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <div
              class="bg-[#1a1b1e] rounded-lg p-2 border border-[#2a2b30] cursor-grab active:cursor-grabbing transition-opacity {dragIdx === i ? 'opacity-40' : ''}"
              draggable="true"
              role="listitem"
              ondragstart={() => { dragIdx = i; }}
              ondragend={() => { dragIdx = null; }}
              ondragover={(e) => { e.preventDefault(); e.dataTransfer!.dropEffect = "move"; }}
              ondrop={() => { if (dragIdx !== null && dragIdx !== i) { appState.reorderDownloads(dragIdx, i); } dragIdx = null; }}
            >
              <div class="flex items-center justify-between mb-1">
                <span class="text-[11px] text-gray-300 truncate flex-1 mr-2" title={dl.fileName}>{dl.fileName}</span>
                <div class="flex items-center gap-1.5 shrink-0">
                  {#if isQueued}
                    <span class="text-[11px] text-[#f59f00] font-medium">#{i + 1} queued</span>
                  {:else if speedStr}
                    <span class="text-[11px] text-[#60a5fa] font-medium">{speedStr}</span>
                  {/if}
                  <button
                    class="w-4 h-4 rounded-full flex items-center justify-center text-[#71717a] hover:text-white hover:bg-[#e03131] transition-colors cursor-pointer"
                    title="Cancel download"
                    onclick={async (e) => { e.stopPropagation(); try { const api = await import('./api'); await api.deleteDownload(dl.id); } catch {} }}
                    aria-label="Cancel download"
                  >
                    <svg class="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M18 6L6 18M6 6l12 12"/></svg>
                  </button>
                </div>
              </div>
              {#if isRunning}
                <div class="h-1 rounded-full bg-[#2a2b30] overflow-hidden mb-1">
                  <div class="h-full rounded-full bg-[#2563eb] transition-all duration-500" style="width:{dl.progress}%"></div>
                </div>
                <div class="text-[10px] text-[#a1a1aa]">
                  {fmtBytes(dl.bytesDownloaded || 0)}/{fmtBytes(dl.bytesTotal || 0)} · {dl.progress}%{speedStr ? ` · ${speedStr}` : ""}{etaStr ? ` · ${etaStr}` : ""}
                </div>
              {:else if isQueued}
                <div class="h-1 rounded-full bg-[#2a2b30] overflow-hidden">
                  <div class="h-full rounded-full bg-[#f59f00]/40" style="width:100%"></div>
                </div>
              {/if}
            </div>
          {/each}
        </div>
      </div>
    {/if}
  </div>
</aside>
