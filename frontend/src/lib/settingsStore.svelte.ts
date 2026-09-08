import { getSettings, setSettings as apiSetSettings, validateApiKey, ingestLicenseKey, getLicenseStatus, getFrontendConfig, getInstalledVersions } from "./api";
import { isApiKeyDeleteCommand } from "./settings-input";
import type { FrontendConfig } from "./stores/types";

export function createSettingsStore() {
  let nsfwBlurEnabled = $state(true);
  let apiKey = $state("");
  let apiKeyConfigured = $state(false);
  let apiKeyValid = $state<boolean | null>(null);
  let licenseActive = $state(false);
  let settingsLoaded = $state(false);
  let config = $state<FrontendConfig | null>(null);
  let onlyInstalled = $state(false);
  let fastSearch = $state(false);
  let savedPeriod = $state("AllTime");

  function parseSettingArr(...vals: unknown[]): string[] {
    for (const v of vals) {
      if (Array.isArray(v)) return v.map(String);
      if (typeof v === "string" && v) {
        try { const p = JSON.parse(v); if (Array.isArray(p)) return p; } catch {}
        return [v];
      }
    }
    return [];
  }

  async function loadSettings(
    onFiltersLoaded: (settings: any) => void,
    onUnlockedBuzzLoaded: (ids: Set<number>) => void,
  ) {
    try {
      const result: any = await getSettings();
      const settings: any = result?.settings || result || {};
      const capabilities: any = result?.capabilities || {};
      onFiltersLoaded(settings);
      fastSearch = settings.fastSearch ?? false;
      onlyInstalled = settings.onlyInstalled ?? false;
      nsfwBlurEnabled = settings.nsfwBlur ?? true;
      apiKey = "";
      apiKeyConfigured = capabilities.hasCivitaiRedApiKey === true;
      apiKeyValid = apiKeyConfigured ? true : null;
      try {
        const bIds = JSON.parse(settings.unlockedBuzzModelIds || "[]");
        if (Array.isArray(bIds)) onUnlockedBuzzLoaded(new Set(bIds));
      } catch {}
    } catch (e) {
      console.error("[CivBro] loadSettings failed:", e);
    } finally {
      settingsLoaded = true;
    }
  }

  async function loadLicenseStatus() {
    try {
      const status = await getLicenseStatus();
      licenseActive = status.active;
    } catch {
      licenseActive = false;
    }
  }

  async function loadConfig() {
    try {
      config = await getFrontendConfig();
    } catch (e) {
      console.debug("[CivBro] loadConfig failed:", e);
    }
  }

  let saveSettingsTimer: ReturnType<typeof setTimeout> | null = null;

  function saveSettings(
    filters: { nsfw: boolean; modelType: string[]; baseModel: string[]; sort: string; period: string; eaOnly: boolean; updatedOnly: boolean },
    unlockedBuzzModelIds: Set<number>,
  ) {
    if (saveSettingsTimer) clearTimeout(saveSettingsTimer);
    saveSettingsTimer = setTimeout(() => {}, 100);
    apiSetSettings({
      showNsfw: filters.nsfw,
      defaultModelTypes: JSON.stringify(filters.modelType),
      defaultBaseModels: JSON.stringify(filters.baseModel),
      defaultSort: filters.sort,
      defaultPeriod: filters.period,
      nsfwBlur: nsfwBlurEnabled,
      eaOnly: filters.eaOnly,
      updatedOnly: filters.updatedOnly,
      fastSearch,
      onlyInstalled,
      unlockedBuzzModelIds: JSON.stringify([...unlockedBuzzModelIds]),
    }).catch((e) => {
      console.error("[CivBro] saveSettings failed:", e);
    });
  }

  async function validateAndSaveKey(key: string) {
    const normalized = key.trim();
    if (!normalized || isApiKeyDeleteCommand(normalized)) {
      apiKey = "";
      apiKeyConfigured = false;
      apiKeyValid = null;
      await apiSetSettings({ civitaiRedApiKey: "" });
      return;
    }
    apiKey = normalized;
    try {
      const result = await validateApiKey(normalized);
      apiKeyValid = result.valid;
      if (result.valid) apiKeyConfigured = true;
    } catch {
      apiKeyValid = false;
    }
  }

  async function ingestLicense(key: string): Promise<{ status: string; message: string }> {
    try {
      const result = await ingestLicenseKey(key);
      if (result.status === "ok") licenseActive = true;
      return result;
    } catch {
      return { status: "error", message: "Network error" };
    }
  }

  function cleanup() {
    if (saveSettingsTimer) { clearTimeout(saveSettingsTimer); saveSettingsTimer = null; }
  }

  return {
    get nsfwBlurEnabled() { return nsfwBlurEnabled; },
    set nsfwBlurEnabled(v: boolean) { nsfwBlurEnabled = v; },
    get apiKey() { return apiKey; },
    set apiKey(v: string) { apiKey = v; },
    get apiKeyConfigured() { return apiKeyConfigured; },
    get apiKeyValid() { return apiKeyValid; },
    set apiKeyValid(v: boolean | null) { apiKeyValid = v; },
    get licenseActive() { return licenseActive; },
    get settingsLoaded() { return settingsLoaded; },
    set settingsLoaded(v: boolean) { settingsLoaded = v; },
    get config() { return config; },
    get onlyInstalled() { return onlyInstalled; },
    set onlyInstalled(v: boolean) { onlyInstalled = v; },
    get fastSearch() { return fastSearch; },
    set fastSearch(v: boolean) { fastSearch = v; },
    get savedPeriod() { return savedPeriod; },
    set savedPeriod(v: string) { savedPeriod = v; },
    loadSettings, loadConfig, saveSettings, validateAndSaveKey, ingestLicense, loadLicenseStatus, cleanup,
  };
}
