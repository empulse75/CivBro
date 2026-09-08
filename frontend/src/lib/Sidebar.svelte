<script lang="ts">
  import { appState } from "./stores.svelte.ts";
  import type { CivitaiModel } from "./stores/types";
  import { onDestroy } from "svelte";
  import { fmtSize, fmtSpeed, fmtEta } from "./format.ts";
  import { isApiKeyDeleteCommand } from "./settings-input";
  import { deleteDownload } from "./api";

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
  let apiKeyTipTimer: ReturnType<typeof setTimeout>;
  let showApiKeyTip = $state(false);
  let dragIdx = $state<number | null>(null);
  let licensePopup = $state<{ message: string; type: "ok" | "invalid" } | null>(null);
  let licensePopupTimer: ReturnType<typeof setTimeout>;
  let settingsSynced = $state(false);

  onDestroy(() => {
    clearTimeout(debounceTimer);
    clearTimeout(fuzzyTimer);
    clearTimeout(keyDebounceTimer);
    clearTimeout(apiKeyTipTimer);
    clearTimeout(licensePopupTimer);
  });

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
    if (appState.settingsLoaded && !settingsSynced) {
      settingsSynced = true;
      searchInput = appState.filters.search;
      if (appState.apiKeyConfigured) {
        apiKeyInput = "";
        apiKeyValidationStatus = "valid";
      }
    }
  });

  function handleKeyChange() {
    clearTimeout(keyDebounceTimer);
    const val = apiKeyInput.trim();
    if (isApiKeyDeleteCommand(val)) {
      apiKeyValidationStatus = "checking";
      keyDebounceTimer = setTimeout(async () => {
        await appState.validateAndSaveKey(val);
        apiKeyInput = "";
        apiKeyValidationStatus = null;
      }, 600);
      return;
    }
    if (!val) {
      apiKeyValidationStatus = null;
      appState.validateAndSaveKey("");
      return;
    }

    if (val.toUpperCase().startsWith("CIVBRO-")) {
      apiKeyValidationStatus = "checking";
      keyDebounceTimer = setTimeout(async () => {
        const result = await appState.ingestLicense(val);
        if (result.status === "ok") {
          apiKeyInput = "";
          apiKeyValidationStatus = appState.apiKeyValid === true ? "valid"
            : appState.apiKeyValid === false ? "invalid" : null;
          licensePopup = { message: "License activated", type: "ok" };
        } else {
          apiKeyInput = "";
          apiKeyValidationStatus = appState.apiKeyConfigured ? "valid" : "invalid";
          licensePopup = { message: result.message || "Invalid license key", type: "invalid" };
        }
        clearTimeout(licensePopupTimer);
        licensePopupTimer = setTimeout(() => { licensePopup = null; }, 4000);
      }, 600);
      return;
    }

    apiKeyValidationStatus = "checking";
    keyDebounceTimer = setTimeout(async () => {
      await appState.validateAndSaveKey(val);
      apiKeyValidationStatus = appState.apiKeyValid === true ? "valid"
        : appState.apiKeyValid === false ? "invalid" : null;
    }, 600);
  }

  function startApiKeyTip() {
    clearTimeout(apiKeyTipTimer);
    apiKeyTipTimer = setTimeout(() => { showApiKeyTip = true; }, 1500);
  }

  function stopApiKeyTip() {
    clearTimeout(apiKeyTipTimer);
    showApiKeyTip = false;
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
      e.preventDefault();
      searchInput = (e.target as HTMLInputElement).value;
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
      ? "bg-[#67e8c6] text-[#0b1018] font-semibold border-transparent shadow-sm shadow-[#67e8c6]/15"
      : "bg-[#1a2636] text-[#a0b2c6] hover:bg-[#223246] hover:text-[#ecf4fb] border border-[#2a3a4e]/60";
  }

  function isCategorySelected(val: string) {
    if (val === "") return appState.filters.modelType.length === 0;
    return appState.filters.modelType.includes(val);
  }

  function isBaseModelSelected(val: string) {
    if (val === "") return appState.filters.baseModel.length === 0;
    return appState.filters.baseModel.includes(val);
  }

  function categoryChipClass(val: string) {
    return chipClass(isCategorySelected(val));
  }

  function baseModelChipClass(val: string) {
    return chipClass(isBaseModelSelected(val));
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

  function fmtBytes(b: number) { return fmtSize(b); }

</script>

<aside class="w-full h-full min-h-0 flex flex-col overflow-hidden bg-[#0b1018] border-r border-[#2a3a4e] text-[#ecf4fb] selection:bg-[#67e8c6]/30 selection:text-[#67e8c6]">
  <!-- Compact Studio Branding Header -->
  <div class="px-4 py-3 border-b border-[#2a3a4e]/60 bg-[#131c29]/50 backdrop-blur-sm flex items-center justify-between gap-3 shrink-0">
    <div class="flex items-center gap-2.5 min-w-0">
      <div class="w-7 h-7 rounded-lg bg-gradient-to-br from-[#67e8c6]/20 via-[#1a2636] to-[#b7a4ff]/20 border border-[#2a3a4e] flex items-center justify-center p-1 shrink-0 shadow-sm shadow-[#67e8c6]/10">
        <svg class="w-full h-full" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="civ-logo-grad" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stop-color="#67e8c6" />
              <stop offset="100%" stop-color="#b7a4ff" />
            </linearGradient>
            <linearGradient id="civ-accent-grad" x1="0" y1="32" x2="32" y2="0" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stop-color="#ffc982" />
              <stop offset="100%" stop-color="#67e8c6" />
            </linearGradient>
          </defs>
          <path d="M16 4L26 9.5V22.5L16 28L6 22.5V9.5L16 4Z" stroke="url(#civ-logo-grad)" stroke-width="2.5" stroke-linejoin="round" />
          <path d="M16 4V16M26 9.5L16 16M6 9.5L16 16" stroke="url(#civ-logo-grad)" stroke-width="1.5" stroke-linecap="round" />
          <circle cx="16" cy="16" r="3" fill="url(#civ-accent-grad)" />
        </svg>
      </div>
      <div class="flex flex-col min-w-0">
        <div class="flex items-center gap-1.5">
          <span class="text-sm font-black tracking-tight text-[#ecf4fb]">Civ<span class="text-[#67e8c6]">Bro</span></span>
          <span class="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-extrabold bg-[#67e8c6]/10 text-[#67e8c6] border border-[#67e8c6]/25 uppercase tracking-widest leading-none">Studio</span>
        </div>
        <p class="text-[10.5px] font-medium text-[#a0b2c6] tracking-wide truncate">Civitai Model Studio</p>
      </div>
    </div>
  </div>
  <!-- Studio intro: the workspace hero lives here so the grid gets the full
       workspace height. Copy tracks the active tab like the old hero did. -->
  <div class="px-4 pt-2.5 pb-3 border-b border-[#2a3a4e]/60 shrink-0">
    <p class="text-[8px] font-bold tracking-[1.8px] uppercase text-[#a0b2c6]/80">
      {appState.activeTab === "browse" ? "A playground for your imagination" : "The keepers. The favourites. The what-ifs."}
    </p>
    <h1 class="mt-1 text-[17px] leading-[1.18] font-bold tracking-[-0.4px] text-[#ecf4fb]">
      {appState.activeTab === "browse" ? "Find your next" : "Good finds."}
      <span class="text-[#67e8c6]">{appState.activeTab === "browse" ? "happy accident." : "All yours."}</span>
    </h1>
    <p class="mt-1 text-[10.5px] leading-[1.55] text-[#a0b2c6]">
      {appState.activeTab === "browse"
        ? "Fresh inspiration, remarkable models. Make something a little unexpected."
        : "Your local model library, ready for whatever you dream up next."}
    </p>
    <p class="mt-1 text-[10px] italic text-[#ffc982]" style="font-family: Georgia, serif;">
      <svg class="inline w-3 h-3 -mt-0.5 mr-0.5" viewBox="0 0 24 24" fill="#ffc982" aria-hidden="true"><path d="m12 2 2.4 6.9L21 11l-6.6 2.1L12 20l-2.4-6.9L3 11l6.6-2.1Z" /></svg>
      Stay curious.
    </p>
  </div>

  <!-- Scrollable Control Rail -->
  <div class="flex-1 overflow-y-auto px-3.5 py-3 flex flex-col gap-4 text-xs scrollbar-thin scrollbar-thumb-[#2a3a4e] scrollbar-track-transparent">
    <!-- Search Section -->
    <div class="space-y-1.5">
      <label for="sidebar-search-input" class="sr-only">Search models</label>
      <div class="flex gap-2">
        <div class="relative flex-1">
          <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#a0b2c6] pointer-events-none z-10" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd" />
          </svg>
          <input
            id="sidebar-search-input"
            type="text"
            placeholder="Search models..."
            class="w-full pl-9 pr-3 py-2 text-xs bg-[#131c29] border border-[#2a3a4e] rounded-xl text-[#ecf4fb]
              placeholder-[#a0b2c6]/60 outline-none focus:border-[#67e8c6] focus:ring-1 focus:ring-[#67e8c6] transition-all duration-200"
            value={searchInput}
            oninput={(e) => handleSearchInput((e.target as HTMLInputElement).value)}
            onkeydown={handleSearchKeydown}
            onfocus={() => (searchFocused = true)}
            onblur={() => setTimeout(() => (searchFocused = false), 200)}
          />
        </div>
        <button
          class="px-3.5 py-2 text-xs font-semibold bg-[#67e8c6] hover:bg-[#52d1b0] active:scale-[0.98] text-[#0b1018] rounded-xl
            transition-all duration-150 shrink-0 shadow-sm shadow-[#67e8c6]/20 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#67e8c6]"
          onclick={handleSearchClick}
          aria-label="Search"
        >
          Search
        </button>
      </div>
      {#if searchFocused && appState.suggestions.length > 0 && searchInput.length >= 2}
        <div class="relative mt-1 bg-[#131c29] border border-[#2a3a4e] rounded-xl overflow-hidden z-20 shadow-xl shadow-black/50">
          {#each appState.suggestions as suggestion}
            <button
              class="w-full text-left px-3 py-2 text-xs text-[#a0b2c6] hover:bg-[#1a2636] hover:text-[#ecf4fb]
                transition-colors duration-100 border-b border-[#2a3a4e]/40 last:border-0 focus-visible:bg-[#1a2636] focus-visible:text-[#67e8c6] focus-visible:outline-none"
              onmousedown={() => handleSuggestionClick(suggestion)}
            >
              {suggestion}
            </button>
          {/each}
        </div>
      {/if}
    </div>

    <!-- Category (Model Types) -->
    <div>
      <div class="flex items-center justify-between mb-2">
        <h3 class="text-[11px] font-bold text-[#a0b2c6] uppercase tracking-wider">Model Types</h3>
      </div>
      <div class="flex flex-wrap gap-1.5" role="group" aria-label="Model types">
        {#each categories as cat}
          <button
            class="px-2.5 py-1 text-[11.5px] font-medium rounded-lg transition-all duration-150 border cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#67e8c6] {categoryChipClass(cat.value)}"
            onclick={() => handleCategorySelect(cat.value)}
            aria-pressed={isCategorySelected(cat.value)}
          >
            {cat.label}
          </button>
        {/each}
      </div>
    </div>

    <div class="h-px bg-gradient-to-r from-transparent via-[#2a3a4e]/60 to-transparent my-0.5"></div>

    <!-- Base Model -->
    <div>
      <div class="flex items-center justify-between mb-2">
        <h3 class="text-[11px] font-bold text-[#a0b2c6] uppercase tracking-wider">Base Model</h3>
      </div>
      <div class="flex flex-wrap gap-1.5" role="group" aria-label="Base models">
        {#each baseModels as bm}
          <button
            class="px-2.5 py-1 text-[11.5px] font-medium rounded-lg transition-all duration-150 border cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#67e8c6] {baseModelChipClass(bm.value)}"
            onclick={() => handleBaseModelSelect(bm.value)}
            aria-pressed={isBaseModelSelected(bm.value)}
          >
            {bm.label}
          </button>
        {/each}
      </div>
    </div>

    <div class="h-px bg-gradient-to-r from-transparent via-[#2a3a4e]/60 to-transparent my-0.5"></div>

    <!-- Period -->
    <div>
      <div class="flex items-center justify-between mb-2">
        <h3 class="text-[11px] font-bold text-[#a0b2c6] uppercase tracking-wider">Time Period</h3>
      </div>
      <div class="flex flex-wrap gap-1.5" role="group" aria-label="Time period">
        {#each periods as p}
          <button
            class="px-2.5 py-1 text-[11.5px] font-medium rounded-lg transition-all duration-150 border cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#67e8c6] {chipClass(appState.filters.period === p.value)}"
            onclick={() => handlePeriodSelect(p.value)}
            aria-pressed={appState.filters.period === p.value}
          >
            {p.label}
          </button>
        {/each}
      </div>
    </div>

    <div class="h-px bg-gradient-to-r from-transparent via-[#2a3a4e]/60 to-transparent my-0.5"></div>

    <!-- Sort -->
    <div>
      <div class="flex items-center justify-between mb-2">
        <h3 class="text-[11px] font-bold text-[#a0b2c6] uppercase tracking-wider">Sort Order</h3>
      </div>
      <div class="flex flex-wrap gap-1.5" role="group" aria-label="Sort order">
        {#each sortOptions as s}
          <button
            class="px-2.5 py-1 text-[11.5px] font-medium rounded-lg transition-all duration-150 border cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#67e8c6] {chipClass(appState.filters.sort === s.value)}"
            onclick={() => handleSortSelect(s.value)}
            aria-pressed={appState.filters.sort === s.value}
          >
            {s.label}
          </button>
        {/each}
      </div>
    </div>

    <!-- NSFW Toggles -->
    <div class="border-t border-[#2a3a4e]/60 pt-3">
      <div class="bg-[#131c29]/60 border border-[#2a3a4e]/50 rounded-xl p-3 flex flex-col gap-2.5">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="text-xs font-semibold text-[#ecf4fb]">Show NSFW</span>
            {#if appState.filters.nsfw}
              <span class="px-1.5 py-0.5 text-[9.5px] font-bold text-[#ffc982] bg-[#ffc982]/10 border border-[#ffc982]/30 rounded uppercase tracking-wider">18+</span>
            {/if}
          </div>
          <button
            class="w-10 h-5.5 rounded-full transition-all duration-200 relative p-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#67e8c6] cursor-pointer {appState.filters.nsfw ? 'bg-[#ffc982]' : 'bg-[#1a2636] border border-[#2a3a4e]'}"
            onclick={toggleNsfw}
            role="switch"
            aria-checked={appState.filters.nsfw}
            aria-label="Toggle NSFW content"
          >
            <span class="block w-4 h-4 rounded-full shadow transition-transform duration-200 ease-out {appState.filters.nsfw ? 'translate-x-[18px] bg-[#0b1018]' : 'translate-x-0 bg-[#a0b2c6]'}"></span>
          </button>
        </div>

        <div class="flex items-center justify-between border-t border-[#2a3a4e]/40 pt-2.5">
          <span class="text-xs font-medium text-[#a0b2c6]">Blur NSFW Thumbnails</span>
          <button
            class="w-10 h-5.5 rounded-full transition-all duration-200 relative p-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#67e8c6] cursor-pointer {appState.nsfwBlurEnabled ? 'bg-[#67e8c6]' : 'bg-[#1a2636] border border-[#2a3a4e]'}"
            onclick={toggleNsfwBlur}
            role="switch"
            aria-checked={appState.nsfwBlurEnabled}
            aria-label="Toggle NSFW blur"
          >
            <span class="block w-4 h-4 rounded-full shadow transition-transform duration-200 ease-out {appState.nsfwBlurEnabled ? 'translate-x-[18px] bg-[#0b1018]' : 'translate-x-0 bg-[#a0b2c6]'}"></span>
          </button>
        </div>
      </div>
    </div>

    <!-- Quick Filters -->
    <div class="border-t border-[#2a3a4e]/60 pt-3">
      <h3 class="text-[11px] font-bold text-[#a0b2c6] uppercase tracking-wider mb-2">Quick Filters</h3>
      <div class="flex flex-wrap gap-1.5" role="group" aria-label="Quick filters">
        <button
          class="px-2.5 py-1 text-[11.5px] font-medium rounded-lg border transition-all duration-150 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#67e8c6] {chipClass(appState.filters.eaOnly)}"
          onclick={() => {
            clearTimeout(debounceTimer);
            appState.filters.search = searchInput;
            appState.filters.eaOnly = !appState.filters.eaOnly;
            appState.saveSettings();
            appState.triggerSearch();
          }}
          aria-pressed={appState.filters.eaOnly}
        >
          Early Access
        </button>
        <button
          class="px-2.5 py-1 text-[11.5px] font-medium rounded-lg border transition-all duration-150 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#67e8c6] {chipClass(appState.filters.updatedOnly)}"
          onclick={() => {
            clearTimeout(debounceTimer);
            appState.filters.search = searchInput;
            appState.filters.updatedOnly = !appState.filters.updatedOnly;
            appState.saveSettings();
            appState.triggerSearch();
          }}
          aria-pressed={appState.filters.updatedOnly}
        >
          Updated (48h)
        </button>
      </div>
    </div>

    <!-- Additional Settings Toggles -->
    <div class="border-t border-[#2a3a4e]/60 pt-3 space-y-2.5">
      <div class="flex items-center justify-between">
        <div class="flex flex-col">
          <span class="text-xs font-semibold text-[#ecf4fb]">Only Installed</span>
          <span class="text-[10px] text-[#a0b2c6]">Local models only</span>
        </div>
        <button
          class="w-10 h-5.5 rounded-full transition-all duration-200 relative p-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#67e8c6] cursor-pointer {appState.onlyInstalled ? 'bg-[#67e8c6]' : 'bg-[#1a2636] border border-[#2a3a4e]'}"
          onclick={() => {
            appState.onlyInstalled = !appState.onlyInstalled;
            appState.saveSettings();
          }}
          role="switch"
          aria-checked={appState.onlyInstalled}
          aria-label="Show only locally installed models"
        >
          <span class="block w-4 h-4 rounded-full shadow transition-transform duration-200 ease-out {appState.onlyInstalled ? 'translate-x-[18px] bg-[#0b1018]' : 'translate-x-0 bg-[#a0b2c6]'}"></span>
        </button>
      </div>

      <div class="flex items-center justify-between border-t border-[#2a3a4e]/40 pt-2.5">
        <div class="flex flex-col">
          <span class="text-xs font-semibold text-[#ecf4fb]">Fast Search</span>
          <span class="text-[10px] text-[#a0b2c6]">Bypass time period limit</span>
        </div>
        <button
          class="w-10 h-5.5 rounded-full transition-all duration-200 relative p-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#67e8c6] cursor-pointer {appState.fastSearch ? 'bg-[#b7a4ff]' : 'bg-[#1a2636] border border-[#2a3a4e]'}"
          onclick={() => { appState.fastSearch = !appState.fastSearch; appState.saveSettings(); }}
          role="switch"
          aria-checked={appState.fastSearch}
          aria-label="Use AllTime period for search-box queries (keeps other filters intact)"
        >
          <span class="block w-4 h-4 rounded-full shadow transition-transform duration-200 ease-out {appState.fastSearch ? 'translate-x-[18px] bg-[#0b1018]' : 'translate-x-0 bg-[#a0b2c6]'}"></span>
        </button>
      </div>
    </div>

    <!-- License Popup -->
    {#if licensePopup}
      <div class="border-t border-[#2a3a4e]/60 pt-3 relative">
        <div class="flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium transition-all duration-300 {licensePopup.type === 'ok' ? 'bg-[#67e8c6]/10 text-[#67e8c6] border border-[#67e8c6]/30' : 'bg-[#ff6b6b]/10 text-[#ff6b6b] border border-[#ff6b6b]/30'}">
          <svg class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            {#if licensePopup.type === 'ok'}
              <path d="M20 6L9 17l-5-5"/>
            {:else}
              <circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/>
            {/if}
          </svg>
          <span>{licensePopup.message}</span>
        </div>
      </div>
    {/if}

    <!-- API Key Container -->
    <div class="border-t border-[#2a3a4e]/60 pt-3">
      <div class="bg-[#131c29]/70 border border-[#2a3a4e]/60 rounded-xl p-3 space-y-2">
        <div class="flex items-center justify-between gap-2">
          <label for="civitai-api-key" class="text-xs font-semibold text-[#ecf4fb]">civitai.red API Key</label>
          {#if apiKeyValidationStatus === 'valid'}
            <span class="text-[9.5px] font-extrabold uppercase tracking-wider text-[#67e8c6] bg-[#67e8c6]/15 border border-[#67e8c6]/30 rounded-md px-1.5 py-0.5 leading-none">valid</span>
          {:else if apiKeyValidationStatus === 'invalid'}
            <span class="text-[9.5px] font-extrabold uppercase tracking-wider text-[#ff6b6b] bg-[#ff6b6b]/15 border border-[#ff6b6b]/30 rounded-md px-1.5 py-0.5 leading-none">invalid</span>
          {:else if apiKeyValidationStatus === 'checking'}
            <span class="text-[9.5px] font-extrabold uppercase tracking-wider text-[#b7a4ff] bg-[#b7a4ff]/15 border border-[#b7a4ff]/30 rounded-md px-1.5 py-0.5 leading-none animate-pulse">checking</span>
          {/if}
        </div>
        <div class="relative flex items-center gap-2" role="group" onmouseenter={startApiKeyTip} onmouseleave={stopApiKeyTip}>
          <input
            id="civitai-api-key"
            type="password"
            placeholder="Enter API key..."
            class="w-full px-3 py-1.5 text-xs bg-[#1a2636] border border-[#2a3a4e] rounded-lg text-[#ecf4fb]
              placeholder-[#a0b2c6]/50 outline-none focus:border-[#67e8c6] focus:ring-1 focus:ring-[#67e8c6] transition-all duration-200"
            bind:value={apiKeyInput}
            oninput={handleKeyChange}
            aria-describedby="api-key-delete-tip"
          />
          {#if showApiKeyTip}
            <div
              id="api-key-delete-tip"
              role="tooltip"
              class="absolute left-0 bottom-[calc(100%+8px)] z-30 w-full rounded-xl border border-[#67e8c6]/40 bg-[#131c29]/95 px-3 py-2 text-[11px] leading-4 text-[#ecf4fb] shadow-2xl backdrop-blur-md"
            >
              Type "delete" to remove your saved API key from extension storage.
            </div>
          {/if}
        </div>
        {#if appState.licenseActive}
          <div class="flex items-center gap-1.5 pt-0.5">
            <svg class="w-3.5 h-3.5 text-[#67e8c6]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M20 6L9 17l-5-5"/></svg>
            <span class="text-[11px] text-[#67e8c6] font-semibold">License Active</span>
          </div>
        {/if}
        <div class="flex items-center gap-1.5 pt-0.5">
          <svg class="w-3.5 h-3.5 text-[#ffc982] shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/><line x1="6" y1="1" x2="6" y2="4"/><line x1="10" y1="1" x2="10" y2="4"/><line x1="14" y1="1" x2="14" y2="4"/>
          </svg>
          <a href="https://ko-fi.com/empulse75" target="_blank" rel="noopener" class="text-[11px] text-[#a0b2c6] hover:text-[#ffc982] transition-colors no-underline font-medium">Buy me a beer?</a>
        </div>
      </div>
    </div>

    <!-- Clear Filters Button -->
    <button
      class="w-full py-2.5 text-xs text-[#a0b2c6] hover:text-[#ecf4fb] bg-[#1a2636] hover:bg-[#223246] border border-[#2a3a4e]
        rounded-xl transition-all duration-150 font-semibold shadow-sm active:scale-[0.99] cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#67e8c6]"
      onclick={() => {
        appState.clearFilters();
        searchInput = "";
        appState.triggerSearch();
      }}
    >
      Clear Filters
    </button>

    <!-- Downloads Container -->
    {#if appState.hasActiveDownloads}
      <div class="border-t border-[#2a3a4e]/60 pt-3">
        <div class="flex items-center justify-between mb-2">
          <span class="text-[11px] font-bold text-[#a0b2c6] uppercase tracking-wider">Active Downloads</span>
          <span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-[#67e8c6]/15 text-[#67e8c6] border border-[#67e8c6]/30">{appState.activeDownloads.length}</span>
        </div>
        <div class="flex flex-col gap-2" role="list">
          {#each appState.activeDownloads as dl, i (dl.id)}
            {@const isRunning = dl.status === "downloading"}
            {@const isQueued = dl.status === "queued" || dl.status === "pending"}
            {@const speedStr = isRunning && dl.speed ? fmtSpeed(dl.speed) : ""}
            {@const etaStr = isRunning && dl.etaSec ? `ETA ${fmtEta(dl.etaSec)}` : ""}
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <div
              class="bg-[#131c29] rounded-xl p-2.5 border border-[#2a3a4e] cursor-grab active:cursor-grabbing transition-all duration-150 hover:border-[#2a3a4e]/90 {dragIdx === i ? 'opacity-40 scale-[0.98]' : ''}"
              draggable="true"
              role="listitem"
              ondragstart={() => { dragIdx = i; }}
              ondragend={() => { dragIdx = null; }}
              ondragover={(e) => { e.preventDefault(); e.dataTransfer!.dropEffect = "move"; }}
              ondrop={() => { if (dragIdx !== null && dragIdx !== i) { appState.reorderDownloads(dragIdx, i); } dragIdx = null; }}
            >
              <div class="flex items-center justify-between mb-1.5 gap-2">
                <span class="text-[11.5px] font-medium text-[#ecf4fb] truncate flex-1" title={dl.fileName}>{dl.fileName}</span>
                <div class="flex items-center gap-1.5 shrink-0">
                  {#if isQueued}
                    <span class="text-[10px] text-[#ffc982] font-bold bg-[#ffc982]/10 border border-[#ffc982]/30 px-1.5 py-0.5 rounded">#{i + 1} queued</span>
                  {:else if speedStr}
                    <span class="text-[10px] text-[#67e8c6] font-bold bg-[#67e8c6]/10 border border-[#67e8c6]/30 px-1.5 py-0.5 rounded">{speedStr}</span>
                  {/if}
                  <button
                    class="w-4.5 h-4.5 rounded-full flex items-center justify-center text-[#a0b2c6] hover:text-white hover:bg-[#ff6b6b] transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#ff6b6b]"
                    title="Cancel download"
                    onclick={async (e) => { e.stopPropagation(); try { await deleteDownload(dl.id); } catch (error) { console.error("[CivBro] Cancel download failed", error); } }}
                    aria-label="Cancel download"
                  >
                    <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 6L6 18M6 6l12 12"/></svg>
                  </button>
                </div>
              </div>
              {#if isRunning}
                <div class="h-1.5 rounded-full bg-[#1a2636] overflow-hidden mb-1.5 border border-[#2a3a4e]/40">
                  <div class="h-full rounded-full bg-gradient-to-r from-[#67e8c6] to-[#b7a4ff] transition-all duration-500" style="width:{dl.progress}%"></div>
                </div>
                <div class="text-[10px] text-[#a0b2c6] flex items-center justify-between font-mono">
                  <span>{fmtBytes(dl.bytesDownloaded || 0)} / {fmtBytes(dl.bytesTotal || 0)}</span>
                  <span>{dl.progress}%{etaStr ? ` · ${etaStr}` : ""}</span>
                </div>
              {:else if isQueued}
                <div class="h-1 rounded-full bg-[#1a2636] overflow-hidden">
                  <div class="h-full rounded-full bg-[#ffc982]/40" style="width:100%"></div>
                </div>
              {/if}
            </div>
          {/each}
        </div>
      </div>
    {/if}
  </div>
</aside>
