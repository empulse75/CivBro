<script lang="ts">
  import { scanLocalModels, deleteLocalModel } from "./api";
  import { appState } from "./stores.svelte.ts";
  import { fmtSize } from "./format.ts";

  let searchQuery = $state("");
  let scanning = $state(false);
  const formatSize = fmtSize;

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

  function formatPath(path: string): string {
    const parts = path.split(/[\\/]/);
    return parts.slice(-2).join("/");
  }
</script>

<div class="library">
  <div class="library-toolbar">
    <label class="library-search">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/></svg>
      <input type="search" placeholder="Find something in your collection…" aria-label="Filter local models" bind:value={searchQuery} />
    </label>
    <div class="library-actions">
      <button class="civ-button primary" onclick={handleScan} disabled={scanning}>
        <svg class:scanning viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4M8 12h8M12 8v8"/></svg>
        {scanning ? "Scanning…" : "Scan models"}
      </button>
      <button class="civ-button civ-icon-button" onclick={() => appState.refreshLocalModels()} aria-label="Refresh collection" title="Refresh collection">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M20 8a8 8 0 1 0 0 8M20 3v5h-5"/></svg>
      </button>
    </div>
  </div>

  <div class="library-content" aria-busy={scanning}>
    {#if filteredModels.length === 0}
      <div class="empty-library" role="status">
        <div class="library-art" aria-hidden="true">
          <svg viewBox="0 0 100 100" fill="none"><rect x="20" y="16" width="48" height="61" rx="10" transform="rotate(-12 20 16)" fill="#67e8c619" stroke="#67e8c655"/><rect x="35" y="20" width="48" height="61" rx="10" transform="rotate(9 35 20)" fill="#25263c" stroke="#b7a4ff"/><path d="m56 35 3 10 10 3-10 3-3 10-3-10-10-3 10-3Z" fill="#b7a4ff"/></svg>
        </div>
        <span class="library-eyebrow">A HOME FOR YOUR NEXT BIG IDEA</span>
        <h2>{searchQuery.trim() ? "No keepers with that name." : "Make room for the good stuff."}</h2>
        <p>{searchQuery.trim() ? "Try another name, model type, or path." : "Already have models? Scan your directories to bring them together here."}</p>
        {#if !searchQuery.trim()}
          <button class="civ-button primary" onclick={handleScan} disabled={scanning}>{scanning ? "Looking through your directories…" : "Discover my local models"}</button>
        {/if}
      </div>
    {:else}
      <div class="library-summary">{filteredModels.length} {filteredModels.length === 1 ? "model" : "models"} in view <span>Ready when inspiration strikes.</span></div>
      <div class="library-list">
        {#each filteredModels as model (model.id)}
          <article class="library-row">
            <div class="model-file-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="m12 3 9 5-9 5-9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/></svg></div>
            <div class="model-info">
              <h3 title={model.name}>{model.name}</h3>
              <div class="model-metadata"><span class="type-chip">{model.type}</span><span>{formatSize(model.size)}</span><span class="model-path" title={model.path}>{formatPath(model.path)}</span></div>
            </div>
            <div class="model-actions">
              {#if model.modelId}
                <button class="library-detail" onclick={() => {
                  appState.activeTab = "browse";
                  appState.openModelDetail({ id: model.modelId!, name: model.name, type: model.type, nsfw: false });
                }}>Details <span aria-hidden="true">↗</span></button>
                <button class="library-remove" onclick={() => handleRemove(model.modelId!)} aria-label={`Remove ${model.name}`}>Remove</button>
              {:else}
                <span class="unlinked">Not linked to Civitai</span>
              {/if}
            </div>
          </article>
        {/each}
      </div>
    {/if}
  </div>
</div>

<style>
  .library { display: flex; flex-direction: column; height: 100%; min-height: 0; }
  .library-toolbar { display: flex; gap: 12px; padding: 0 30px 20px; border-bottom: 1px solid var(--civ-border); flex-shrink: 0; }
  .library-search { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; border: 1px solid var(--civ-border); border-radius: 12px; background: var(--civ-panel); padding: 0 14px; }
  .library-search:focus-within { border-color: var(--civ-accent); box-shadow: 0 0 0 3px #67e8c611; }
  .library-search svg { width: 17px; height: 17px; flex-shrink: 0; color: var(--civ-muted); }
  .library-search input { background: transparent; width: 100%; min-width: 0; min-height: 42px; font-size: 12px; outline: none; color: var(--civ-ink); }
  .library-search input::placeholder { color: var(--civ-muted); }
  .library-actions { display: flex; align-items: center; gap: 8px; }
  .library-content { overflow-y: auto; flex: 1; min-height: 0; padding: 20px 30px; }
  .empty-library { min-height: min(400px, 100%); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; text-align: center; padding: 24px 0; }
  .library-art { width: 108px; height: 108px; }
  .library-eyebrow { font-size: 8px; letter-spacing: 1.8px; color: var(--civ-violet); }
  .empty-library h2 { font-size: clamp(20px, 2.5vw, 28px); letter-spacing: -.7px; font-weight: 600; }
  .empty-library p { max-width: 350px; font-size: 12px; line-height: 1.8; color: var(--civ-muted); }
  .empty-library button { margin-top: 6px; }
  .library-summary { display: flex; justify-content: space-between; gap: 12px; font-size: 11px; color: var(--civ-muted); margin-bottom: 16px; }
  .library-summary span { color: var(--civ-violet); }
  .library-list { display: grid; gap: 10px; }
  .library-row { display: flex; align-items: center; gap: 16px; padding: 16px; background: var(--civ-panel); border: 1px solid var(--civ-border); border-radius: 17px; transition: background .2s, border-color .2s; }
  .library-row:hover { background: var(--civ-panel-raised); border-color: #465773; }
  .model-file-icon { display: grid; place-items: center; width: 44px; height: 48px; flex-shrink: 0; color: var(--civ-violet); background: #b7a4ff0b; border: 1px solid #b7a4ff21; border-radius: 12px; }
  .model-file-icon svg { width: 25px; height: 25px; }
  .model-info { min-width: 0; flex: 1; }
  .model-info h3 { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .model-metadata { display: flex; align-items: center; gap: 9px; margin-top: 8px; font-size: 10px; color: var(--civ-muted); }
  .type-chip { color: var(--civ-accent); background: #67e8c60d; padding: 3px 7px; border-radius: 6px; }
  .model-path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .model-actions { display: flex; align-items: center; gap: 8px; font-size: 11px; }
  .model-actions button { min-height: 36px; padding: 7px 10px; border-radius: 9px; }
  .library-detail { color: var(--civ-accent); background: #67e8c611; }
  .library-detail:hover { background: #67e8c625; }
  .library-remove { color: #ffa6a0; }
  .library-remove:hover { background: #ff99841a; }
  .unlinked { color: var(--civ-muted); font-size: 10px; }
  .scanning { animation: scan-turn 3s linear infinite; }
  @keyframes scan-turn { to { transform: rotate(360deg); } }
  @media (max-width: 600px) {
    .library-toolbar { padding: 0 18px 16px; flex-wrap: wrap; }
    .library-search { flex-basis: 100%; }
    .library-content { padding: 18px; }
    .library-row { flex-wrap: wrap; gap: 12px; padding: 13px; }
    .model-actions { width: 100%; padding-left: 56px; justify-content: flex-end; }
    .library-summary span, .model-path { display: none; }
  }
</style>
