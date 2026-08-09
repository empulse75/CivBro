<script lang="ts">
  import DOMPurify from "dompurify";
  import { appState } from "./stores.svelte.ts";
  import type { CivitaiModel, ModelVersion, ModelFile, ModelDependency } from "./stores/types";
  import { fmtCount, fmtSize, fmtSpeed, fmtEta, fmtAgo } from "./format.ts";
  import { subdirForFile, subdirForType, imgSrc } from "./paths.ts";
  import PopupLightbox from "./PopupLightbox.svelte";
  import PopupGallery from "./PopupGallery.svelte";
  import PopupCarousel from "./PopupCarousel.svelte";
  import CreatorCard from "./CreatorCard.svelte";
  import { getModelComments, getSuggestedResources } from "./api.ts";

  function sanitizeHtml(dirty: string): string {
    return DOMPurify.sanitize(dirty, {
      ALLOWED_TAGS: ["a","b","i","em","strong","p","br","ul","ol","li","h1","h2","h3","h4","h5","h6","blockquote","pre","code","img","hr","span","div","table","thead","tbody","tr","th","td","caption","colgroup","col","sup","sub","del","s","u","details","summary"],
      ALLOWED_ATTR: ["href","target","rel","src","alt","width","height","title","class","id","style","colspan","rowspan","scope"],
    });
  }

  interface Props {
    model: CivitaiModel;
    versions: ModelVersion[];
    selectedVersion: ModelVersion | null;
    installedVersionIds?: number[];
    onClose: () => void;
    onSelectVersion: (v: ModelVersion) => void;
  }

  let { model, versions, selectedVersion, installedVersionIds = [], onClose, onSelectVersion }: Props = $props();

  let installedSet = $derived(new Set(installedVersionIds));

  const MODELS_ROOT = $derived(appState.config?.modelsRoot || "");
  const DIR_MAP = $derived(appState.config?.frontendDirMap || {});

  // Map a component/file type (or filename) to the correct WebUI subdirectory.
  // Fixes VAE / text-encoder files landing in the checkpoint folder.
  function subDir(t: string): string { return subdirForType(t, DIR_MAP); }
  function fileTargetDir(file: ModelFile): string {
    return subdirForFile(file.type || "", file.name || "", modelType, DIR_MAP);
  }
  function depDir(dep: ModelDependency): string {
    const byType = subDir(dep.type || "");
    if (byType) return byType;
    const n = (dep.name || dep.modelName || "").toLowerCase();
    if (/vae/.test(n)) return "VAE";
    if (/encoder|(^|[_\-.])te([_\-.]|$)|txt|t5|clip/.test(n)) return "text_encoder";
    return "Stable-diffusion";
  }

  let activeImg = $state(0);
  let showLb = $state(false);
  let lbIdx = $state(0);
  let galleryVisible = $state(12);
  let galSentinel = $state<HTMLDivElement | null>(null);
  // Per-download state lives in the global store so progress persists across popup
  // open/close. See appState.downloads / queueDownload / pollDownloads.
  interface DlState { fileId: number | null; versionId: number; status: string; progress: number; bytesDownloaded?: number; bytesTotal?: number; speed?: number; etaSec?: number; error?: string }
  let copied = $state("");
  let comments = $state<Array<{id: number; content: string; createdAt: string; user: {username: string; image?: string} | null}>>([]);
  let commentsCursor = $state<string | null>(null);
  let commentsLoading = $state(false);
  let suggestions = $state<Array<{id: number; name: string; type: string; nsfw: boolean; stats: Record<string,number>; images: Array<{url: string; type: string}>}>>([]);

  async function loadComments() {
    try {
      const r = await getModelComments(model.id);
      comments = r.comments || [];
      commentsCursor = r.nextCursor || null;
    } catch {}
  }
  async function loadMoreComments() {
    if (!commentsCursor || commentsLoading) return;
    commentsLoading = true;
    try {
      const r = await getModelComments(model.id, commentsCursor);
      comments = [...comments, ...(r.comments || [])];
      commentsCursor = r.nextCursor || null;
    } catch {}
    commentsLoading = false;
  }

  $effect(() => {
    if (model?.id) {
      loadComments();
      getSuggestedResources(model.id).then(r => { suggestions = r.items || []; }).catch(() => {});
    }
  });

  let galleryImages = $derived.by(() => {
    const all: any[] = [];
    const seen = new Set<string>();
    const collect = (imgs: any[]) => {
      for (const img of imgs) {
        if (img?.url && !seen.has(img.url)) {
          seen.add(img.url);
          all.push(img);
        }
      }
    };
    if (selectedVersion?.images) collect(selectedVersion.images);
    for (const v of versions) {
      if (v.id !== selectedVersion?.id && v.images) collect(v.images);
    }
    return all;
  });

  $effect(() => {
    if (!galSentinel) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && galleryVisible < galleryImages.length) {
          galleryVisible += 12;
        }
      },
      { rootMargin: "200px" }
    );
    obs.observe(galSentinel);
    return () => obs.disconnect();
  });


  let files = $derived<ModelFile[]>((selectedVersion?.files as ModelFile[]) || []);
  // Civitai groups a version's files: the actual model checkpoint(s)/LoRA go in the
  // Download box; auxiliary files (VAE, Text Encoder, Config…) are "Required Components".
  function isComponentType(t: string | undefined): boolean {
    const s = (t || "").toLowerCase();
    return s.includes("vae") || s.includes("encoder") || s.includes("config") || s.includes("negative") || s.includes("archive");
  }
  // Category used to pick a type-specific icon + label for a file/component.
  function typeCat(t: string | undefined): string {
    const s = (t || "").toLowerCase();
    if (s.includes("vae")) return "vae";
    if (s.includes("encoder") || s === "te") return "te";
    if (s.includes("lora") || s.includes("locon") || s.includes("dora")) return "lora";
    if (s.includes("embed") || s.includes("textualinversion")) return "embedding";
    if (s.includes("controlnet")) return "controlnet";
    if (s.includes("config")) return "config";
    if (s.includes("checkpoint") || s.includes("model")) return "checkpoint";
    return "other";
  }
  function typeLabel(t: string | undefined): string {
    const c = typeCat(t);
    return { vae: "VAE", te: "Text Encoder", lora: "LoRA", embedding: "Embedding", controlnet: "ControlNet", config: "Config", checkpoint: "Checkpoint", other: t || "File" }[c] || (t || "File");
  }
  let modelFiles = $derived(files.filter((f) => !isComponentType(f.type)));
  let componentFiles = $derived(files.filter((f) => isComponentType(f.type)));
  let modelType = $derived(model.type || (model as any).modelType || "");
  let isBuzzModel = $derived.by(() => {
    if (selectedVersion && (selectedVersion as any).availability === 'EarlyAccess') return true;
    if (selectedVersion && (selectedVersion as any).buzzCost > 0) return true;
    return false;
  });
  let anyVersionBuzz = $derived.by(() => {
    if ((model as any).hasBuzz === true) return true;
    if ((model as any).availability === 'EarlyAccess') return true;
    return versions.some((v: any) => v.availability === 'EarlyAccess');
  });
  let isGenerationOnly = $derived.by(() => {
    if ((model as any).mode === "GenerationOnly") return true;
    if (versions.length > 0 && versions.every((v: any) => {
      const fs = v.files || [];
      return fs.length === 0 || fs.every((f: any) => !f.downloadUrl);
    })) return true;
    return false;
  });
  let hashStr = $derived.by(() => {
    const h = (files.find((f) => f.primary) || files[0])?.hashes || {};
    return (h as any).AutoV2 || (h as any).AutoV1 || (h as any).SHA256?.slice(0, 12) || "";
  });
  let published = $derived.by(() => {
    const d = selectedVersion?.createdAt;
    if (!d) return "";
    try {
      return new Date(d).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
    } catch {
      return "";
    }
  });

  let modelTags = $derived(Array.isArray(model.tags) ? model.tags.filter(Boolean).slice(0, 20) : []);
  let review = $derived.by(() => {
    const s: any = model.stats || {};
    const up = s.thumbsUpCount || 0;
    const down = s.thumbsDownCount || 0;
    const total = up + down;
    if (total < 1) return null;
    const r = up / total;
    const label =
      r >= 0.95 ? "Overwhelmingly Positive" :
      r >= 0.85 ? "Very Positive" :
      r >= 0.7 ? "Positive" :
      r >= 0.5 ? "Mixed" :
      r >= 0.3 ? "Negative" : "Very Negative";
    return { label, total, positive: r >= 0.7 };
  });

  function fmtS(kb: number) {
    if (!kb) return "";
    if (kb >= 1e6) return (kb / 1e6).toFixed(2) + " GB";
    if (kb >= 1e3) return (kb / 1e3).toFixed(1) + " MB";
    return kb.toFixed(0) + " KB";
  }


  function copyWord(w: string) {
    navigator.clipboard?.writeText(w);
    copied = w;
    setTimeout(() => {
      if (copied === w) copied = "";
    }, 1200);
  }

  const DL_ACTIVE = ["pending", "queued", "downloading"];
  function fileDl(fileId: number, versionId: number): (DlState & { id: string }) | null {
    let latest: (DlState & { id: string }) | null = null;
    const dls = appState.downloads;
    for (const id in dls) {
      const d = dls[id];
      if (d.fileId === fileId && d.versionId === versionId) latest = { id, ...d };
    }
    return latest;
  }
  function isActive(d: DlState | null): boolean {
    return !!d && DL_ACTIVE.includes(d.status);
  }
  function fStatus(id: number | null | undefined): string {
    return id != null && selectedVersion ? appState.fileStatus[`${selectedVersion.id}:${id}`] || "" : "";
  }
  function isInstalled(id: number | null | undefined): boolean {
    return fStatus(id) === "installed";
  }

  async function download(file: ModelFile) {
    if (!selectedVersion) return;
    const dl = fileDl(file.id, selectedVersion.id);
    if (isActive(dl)) return;
    if (isInstalled(file.id) && dl?.status !== "failed" && dl?.status !== "gone") return;
    if (fileNeedsApiKey(file)) { window.open("https://civitai.com/models/" + model.id, "_blank"); return; }
    const url = file.downloadUrl || (selectedVersion as any)?.downloadUrl;
    if (!url) return;
    const dir = `${MODELS_ROOT}/${fileTargetDir(file)}`;
    try {
      await appState.queueDownload({
        modelId: model.id,
        versionId: selectedVersion.id,
        fileId: file.id,
        downloadUrl: url,
        downloadDir: dir,
        fileName: file.name,
        fileType: file.type,
        modelType,
        sizeKB: file.sizeKB,
      });
    } catch (e) {
      const id = `err-${file.id}-${Date.now()}`;
      appState.downloads = { ...appState.downloads, [id]: { fileId: file.id, versionId: selectedVersion.id, modelId: model.id, fileName: file.name, status: "failed", progress: 0, error: e instanceof Error ? e.message : "Download failed" } };
    }
  }

  async function downloadDep(dep: ModelDependency) {
    const dl = fileDl(dep.fileId ?? -1, dep.versionId);
    if (isActive(dl)) return; // already downloading this file+version
    if (isInstalled(dep.fileId) && dl?.status !== "failed" && dl?.status !== "gone") return; // healthy install — skip
    const dir = `${MODELS_ROOT}/${depDir(dep)}`;
    try {
      await appState.queueDownload({
        modelId: dep.modelId ?? 0,
        versionId: dep.versionId,
        fileId: dep.fileId ?? undefined,
        downloadUrl: dep.downloadUrl,
        downloadDir: dir,
        fileName: dep.name,
        fileType: dep.type,
        modelType: dep.type || "Checkpoint",
        sizeKB: dep.sizeKB,
      });
    } catch (e) {
      const id = `errdep-${dep.versionId}-${Date.now()}`;
      appState.downloads = { ...appState.downloads, [id]: { fileId: dep.fileId ?? null, versionId: dep.versionId, modelId: dep.modelId ?? 0, fileName: dep.name, status: "failed", progress: 0, error: e instanceof Error ? e.message : "Download failed" } };
    }
  }

  async   function downloadAllDeps() {
    for (const f of componentFiles) {
      await download(f);
    }
    for (const dep of selectedVersion?.dependencies || []) {
      await downloadDep(dep);
    }
  }

  // Temporary search for a tag: closes the popup, sets only the search + type filter
  // (from the originating model), clears everything else, and triggers a one-off search.
  // Sidebar filter state (and its saved settings) are NOT changed.
  function searchByTag(tag: string) {
    onClose();
    appState.setFilter("search", tag);
    appState.setFilter("modelType", [modelType]);
    (appState.filters as any).baseModel = [];
    (appState.filters as any).sort = "Most Downloaded";
    (appState.filters as any).period = "AllTime";
    appState.triggerSearch();
  }

  // Civitai-style scan/verified status of a file.
  function scanState(f: ModelFile): { label: string; when: string; ok: boolean; pending: boolean } {
    const pickle = (f.pickleScanResult || "").toLowerCase();
    const virus = (f.virusScanResult || "").toLowerCase();
    const scanned = !!f.scannedAt;
    const ok = scanned && pickle === "success" && virus === "success";
    const danger = pickle === "danger" || virus === "danger";
    const pending = !scanned || pickle === "pending" || virus === "pending" || (!ok && !danger);
    return {
      label: ok ? "Verified" : danger ? "Danger" : "Unverified",
      when: f.scannedAt ? fmtAgo(f.scannedAt) : "scan pending",
      ok,
      pending: pending && !danger,
    };
  }

  // Sum of all currently-active download speeds (global, across files + deps).
  let totalSpeed = $derived.by(() => {
    let s = 0;
    const dls = appState.downloads;
    for (const id in dls) {
      if (dls[id].status === "downloading") s += dls[id].speed || 0;
    }
    return s;
  });
  let activeCount = $derived.by(() => {
    let n = 0;
    const dls = appState.downloads;
    for (const id in dls) if (dls[id].status === "downloading") n++;
    return n;
  });

  function eaCountdown(): string {
    const end = selectedVersion?.earlyAccessEndsAt;
    if (!end) return "";
    const t = new Date(end).getTime() - Date.now();
    if (t <= 0) return "";
    const d = Math.floor(t / 86400000);
    const h = Math.floor((t % 86400000) / 3600000);
    const m = Math.floor((t % 3600000) / 60000);
    const parts: string[] = [];
    if (d > 0) parts.push(`${d} day${d > 1 ? "s" : ""}`);
    if (h > 0) parts.push(`${h} hour${h > 1 ? "s" : ""}`);
    if (m > 0 && parts.length < 2) parts.push(`${m} minute${m > 1 ? "s" : ""}`);
    return parts.length ? parts.join(", ") : "";
  }

  function downloadPrimary() {
    if (buzzLocked || anyFileNeedsApiKey) {
      window.open(`https://civitai.com/models/${model.id}`, "_blank");
      return;
    }
    const pf = files.find((f) => f.primary) || files[0];
    if (pf) download(pf);
  }

  // Make the thumbnail carousel scroll horizontally with the mouse wheel.


  // Lazy-load videos (only fetch/play when visible) so a gallery of animated previews
  // doesn't download every full-size video at once.

  // Aggregate state for the primary Download button (reflects the primary file only).
  let primaryFile = $derived(modelFiles.find((f) => f.primary) || modelFiles[0] || null);
  let primaryDl = $derived(
    primaryFile && selectedVersion ? fileDl(primaryFile.id, selectedVersion.id) : null,
  );

  let buzzLocked = $derived.by(() => {
    if (!isBuzzModel) return false;
    return !appState.unlockedBuzzModelIds.has(model.id);
  });

  function fileNeedsApiKey(file: ModelFile): boolean {
    const url = file.downloadUrl || "";
    return url.includes("civitai.red") && !appState.apiKeyConfigured;
  }

  let anyFileNeedsApiKey = $derived.by(() => {
    if (isBuzzModel) return false;
    if (!appState.apiKeyConfigured) {
      for (const v of appState.modelVersions) {
        for (const f of v.files || []) {
          if (fileNeedsApiKey(f)) return true;
        }
      }
    }
    return false;
  });

  // Break the popup out of the WebUI iframe so it covers the whole window.
  // Same-origin (both served from :7860), so window.frameElement is accessible.
  $effect(() => {
    const fe = window.frameElement as HTMLElement | null;
    if (!fe) return;
    const wrap = fe.parentElement;
    const savedFe = fe.getAttribute("style") || "";
    const savedWrap = wrap?.getAttribute("style") || "";
    const full =
      "position:fixed;top:0;left:0;right:0;bottom:0;width:100vw;height:100vh;max-width:none;max-height:none;margin:0;padding:0;border:none;z-index:2147483000;";
    fe.setAttribute("style", full);
    if (wrap) wrap.setAttribute("style", full + "overflow:visible;");
    return () => {
      fe.setAttribute("style", savedFe);
      if (wrap) wrap.setAttribute("style", savedWrap);
    };
  });
</script>

<svelte:window
  onkeydown={(e: KeyboardEvent) => {
    if (e.key === "Escape") onClose();
  }}
/>

<div
  class="popup-backdrop fixed inset-0 z-50 flex items-center justify-center backdrop-in"
  onclick={onClose}
  onkeydown={(e) => { if (e.key === 'Escape') onClose(); }}
  role="presentation"
  data-testid="popup-backdrop"
>
  <div
    class="popup-canvas popup-enter relative w-[94vw] h-[92vh] max-w-[1780px] overflow-hidden flex flex-col"
    role="dialog"
    aria-modal="true"
    tabindex="-1"
    data-testid="popup"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.stopPropagation()}
  >
    <button
      class="absolute top-4 right-4 z-10 text-[#aeb8c8] hover:text-white p-2.5 rounded-full transition-colors popup-close"
      onclick={onClose}
      aria-label="Close"
    >
      <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="5" x2="19" y2="19"/><line x1="19" y1="5" x2="5" y2="19"/></svg>
    </button>

    <!-- BODY -->
    {#snippet typeIcon(t: string | undefined)}
      {@const c = typeCat(t)}
      {#if c === "vae"}
        <!-- VAE: aperture / image codec -->
        <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 3v6M21 12h-6M12 21v-6M3 12h6M12 12l4.5-4.5M12 12l-4.5 4.5"/></svg>
      {:else if c === "te"}
        <!-- Text Encoder: text glyph -->
        <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 5h14M12 5v14M8 19h8"/></svg>
      {:else if c === "lora"}
        <!-- LoRA: tuning sliders -->
        <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 6h10M18 6h2M4 12h2M10 12h10M4 18h6M14 18h6"/><circle cx="16" cy="6" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="12" cy="18" r="2"/></svg>
      {:else if c === "embedding"}
        <!-- Embedding: tag -->
        <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M20.6 13.4l-7.2 7.2a2 2 0 01-2.8 0l-7-7A2 2 0 013 12.2V5a2 2 0 012-2h7.2a2 2 0 011.4.6l7 7a2 2 0 010 2.8z"/><circle cx="7.5" cy="7.5" r="1.3" fill="currentColor"/></svg>
      {:else if c === "controlnet"}
        <!-- ControlNet: node graph -->
        <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="12" cy="18" r="2"/><path d="M7 6h10M6 8l5 8M18 8l-5 8"/></svg>
      {:else if c === "config"}
        <!-- Config: gear -->
        <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.9l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.9-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 01-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.9.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.9 1.7 1.7 0 00-1.5-1H3a2 2 0 010-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.9l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.9.3H9a1.7 1.7 0 001-1.5V3a2 2 0 014 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.9-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.9V9a1.7 1.7 0 001.5 1H21a2 2 0 010 4h-.1a1.7 1.7 0 00-1.5 1z"/></svg>
      {:else if c === "checkpoint"}
        <!-- Checkpoint: stacked layers (full model) -->
        <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 2l9 5-9 5-9-5 9-5z"/><path d="M3 12l9 5 9-5"/><path d="M3 17l9 5 9-5"/></svg>
      {:else}
        <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 3v5h5M9 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5z"/></svg>
      {/if}
    {/snippet}
    <div class="popup-workspace flex-1 flex overflow-hidden min-h-0">
    <!-- LEFT: enlarged viewer + carousel + description -->
    <div class="popup-media-column flex-1 flex flex-col overflow-y-auto min-w-0">
      <div class="popup-viewer p-5 pb-3" data-testid="viewer">
        <PopupGallery
          images={galleryImages}
          activeIdx={activeImg}
          onprev={() => { if (activeImg > 0) activeImg -= 1; }}
          onnext={() => { if (activeImg < galleryImages.length - 1) activeImg += 1; }}
          onopenLb={(idx: number) => { lbIdx = idx; showLb = true; }}
        />
      </div>

      <PopupCarousel
        images={galleryImages}
        activeIdx={activeImg}
        onselect={(i: number) => (activeImg = i)}
      />

      <!-- description -->
      <div class="popup-description px-8 py-8 space-y-7">
        {#snippet prose(html: string)}
          <div
            class="text-[14px] text-[#c1c2c5] leading-relaxed prose prose-invert max-w-3xl
            prose-headings:text-[#e5e7eb] prose-headings:text-[15px] prose-headings:font-medium prose-headings:mt-6 prose-headings:mb-3
            prose-a:text-[#4dabf7] prose-a:no-underline hover:prose-a:underline
            prose-strong:text-[#e5e7eb] prose-strong:font-medium
            prose-p:my-3 prose-ul:my-3 prose-li:my-1
            prose-pre:bg-[#161719] prose-pre:border prose-pre:border-[#2c2e33] prose-pre:rounded-lg prose-pre:text-[13px]
            prose-code:text-[#4dabf7] prose-code:bg-[#25262b] prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-code:text-[12px] prose-code:font-normal prose-code:before:content-none prose-code:after:content-none
            prose-img:rounded-xl prose-img:my-4
            prose-hr:border-[#2c2e33]"
          >
            {@html sanitizeHtml(html)}
          </div>
        {/snippet}

        {#if model.description}
          <div>
            {@render prose(model.description)}
          </div>
        {/if}
        {#if !selectedVersion?.description && !model.description}
          <p class="text-[#5c5f66] italic text-[14px]">No description provided.</p>
        {/if}
            </div>

          <!-- Suggested Resources -->
          {#if suggestions.length > 0}
            <div class="flex items-center gap-3 px-8 pt-6 pb-1">
              <div class="flex-1" style="height:2px;background:linear-gradient(90deg,transparent,rgba(59,130,246,0.4) 15%,rgba(59,130,246,0.4) 85%,transparent);border-radius:1px"></div>
            </div>
            <div class="px-8 pb-4">
              <h3 class="text-[11px] font-semibold text-[#909296] uppercase tracking-[0.1em] mb-3">Suggested Resources</h3>
              <div class="flex gap-3 overflow-x-auto pb-2 civ-hscroll">
                {#each suggestions as s (s.id)}
                  <a
                    href={`https://civitai.com/models/${s.id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    class="shrink-0 w-[180px] rounded-lg overflow-hidden bg-[#1a1b1e] border border-[#2c2e33] hover:border-[#4dabf7] hover:scale-[1.02] transition-all no-underline"
                  >
                    <div class="aspect-[3/4] bg-[#25262b] relative">
                      {#if s.images?.[0]?.url}
                        <img class="absolute inset-0 w-full h-full object-cover object-top" src={imgSrc(s.images[0], 400)} alt="" loading="lazy" />
                      {/if}
                      <div class="absolute bottom-0 left-0 right-0 p-3 bg-gradient-to-t from-black/90 via-black/50 to-transparent">
                        <p class="text-[12px] text-white font-semibold leading-tight line-clamp-2 mb-1">{s.name}</p>
                        <span class="text-[10px] text-[#909296] uppercase font-semibold tracking-wide">{s.type}</span>
                      </div>
                    </div>
                  </a>
                {/each}
              </div>
            </div>
          {/if}

          <!-- user image gallery - inline below model description -->
          {#if galleryImages.length > 0}
            <div class="flex items-center gap-3 px-8 pt-6 pb-1">
              <div class="flex-1" style="height:2px;background:linear-gradient(90deg,transparent,rgba(59,130,246,0.4) 15%,rgba(59,130,246,0.4) 85%,transparent);border-radius:1px"></div>
            </div>
            <div class="px-8 py-3">
              <h3 class="text-[11px] font-semibold text-[#909296] uppercase tracking-[0.1em] mb-3">Gallery</h3>
              <div class="grid gap-2" style="grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));">
                {#each galleryImages.slice(0, galleryVisible) as img, i (img.url || i)}
                  <button
                    class="aspect-square rounded-lg overflow-hidden bg-[#1a1b1e] border border-[#2c2e33] cursor-pointer hover:border-[#4dabf7] transition-colors"
                    onclick={() => { lbIdx = i; showLb = true; }}
                  >
                    {#if img.type === "video"}
                      <video class="w-full h-full object-cover" src={img.url} muted loop playsinline preload="metadata"></video>
                    {:else}
                      <img class="w-full h-full object-cover" src={imgSrc(img, 320)} alt="" loading="lazy" />
                    {/if}
                  </button>
                {/each}
              </div>
              {#if galleryVisible < galleryImages.length}
                <div bind:this={galSentinel} class="h-4"></div>
              {/if}
            </div>
          {/if}
          </div>

    <!-- RIGHT: model name + versions + download + details -->
    <aside class="popup-inspector w-[440px] shrink-0 flex flex-col overflow-y-auto" data-testid="right-col">
      <div class="p-5 flex flex-col gap-5">
        <!-- model name + stats -->
        <div>
          <h1 class="text-[34px] font-bold text-[#c1c2c5] leading-tight tracking-tight">{model.name}</h1>
          {#if selectedVersion?.name}
            <p class="mt-1 text-[15px] font-semibold text-[#909296]">{selectedVersion.name}</p>
          {/if}
          <div class="flex items-center gap-3 mt-2.5 text-[14px] text-[#c1c2c5]">
            <span class="inline-flex items-center gap-1" title="Downloads">
              <svg class="w-[16px] h-[16px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 00-6 0v4M5 9h14l1 12H4L5 9z"/></svg>
              {fmtCount((model.stats || {}).downloadCount || 0)}
            </span>
            <span class="inline-flex items-center gap-1" title="Likes">
              <svg class="w-[16px] h-[16px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 11v10M15 5l-1 6h5.5a1.5 1.5 0 011.5 1.8l-1.3 6A2 2 0 0117 21H7"/></svg>
              {fmtCount((model.stats || {}).thumbsUpCount || 0)}
            </span>
            {#if (model.stats || {}).rating}
              <span class="inline-flex items-center gap-1.5 text-amber-400 font-semibold">
                <svg class="w-[16px] h-[16px]" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
                {((model.stats || {}).rating ?? 0).toFixed(1)}
              </span>
            {/if}
          </div>
          <!-- rating bar -->
          {#if ((model.stats || {}).ratingCount || 0) > 0}
            <div class="mt-2.5 flex items-center gap-2">
              <div class="flex-1 h-1.5 rounded-full bg-[#3f3f46] overflow-hidden">
                <div class="h-full bg-amber-400 rounded-full transition-all" style="width:{Math.min(100, (((model.stats || {}).rating ?? 0) / 5) * 100)}%"></div>
              </div>
              <span class="text-[11px] text-[#71717a] shrink-0">{fmtCount((model.stats || {}).ratingCount || 0)}</span>
            </div>
          {/if}
          <!-- creator -->
          <div class="flex items-center gap-2.5 mt-3">
            {#if model.creator?.image}
              <img class="w-7 h-7 rounded-full object-cover" src={model.creator.image} alt="" />
            {:else}
              <div class="w-7 h-7 rounded-full bg-[#373a40] flex items-center justify-center text-[10px] text-[#9da4ae]">{model.creator?.username?.charAt(0)?.toUpperCase() || "?"}</div>
            {/if}
            <span class="text-[13px] text-[#c1c2c5]">{model.creator?.username || "Unknown"}</span>
          </div>

          <!-- prominent type / base model badges -->
          <div class="flex flex-wrap items-center gap-1.5 mt-3">
            {#if modelType}
              <span class="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-[#4dabf7] bg-[#0d2b45] border border-[#1971c2]/40 px-2 py-1 rounded-md">
                <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16M4 12h16M4 17h10"/></svg>
                {modelType}
              </span>
            {/if}
            {#if selectedVersion?.baseModel}
              <span class="text-[10px] font-bold uppercase tracking-wide text-[#b197fc] bg-[#2a1e45] border border-[#7048e8]/40 px-2 py-1 rounded-md">{selectedVersion.baseModel}</span>
            {/if}
            {#if model.nsfw}
              <span class="text-[10px] font-bold uppercase tracking-wide text-[#ff8787] bg-[#3a1a1a] border border-[#e03131]/40 px-2 py-1 rounded-md">NSFW</span>
            {/if}
          </div>
        </div>

        <!-- version selector -->
        {#if versions.length > 0}
          <div>
            <h3 class="text-[11px] font-semibold text-[#909296] uppercase tracking-[0.1em] mb-2">Versions</h3>
            <div class="flex flex-wrap gap-1.5" data-testid="versions">
              {#each versions as ver (ver.id)}
                {@const inst = installedSet.has(ver.id)}
                {@const buzz = (ver as any).availability === 'EarlyAccess' || (ver as any).buzzCost > 0}
                <button
                  style="padding:4px 10px; position:relative; overflow:hidden"
                  class="rounded-full text-[14px] font-bold leading-tight transition-colors border inline-flex items-center gap-1.5
                    {selectedVersion?.id === ver.id
                      ? (buzz ? 'bg-[#1971c2] text-white border-[#1971c2]' : (inst ? 'bg-[#1971c2] text-white border-[#51cf66]' : 'bg-[#1971c2] text-white border-[#1971c2]'))
                      : (buzz
                          ? 'bg-[#25262b] text-[#c1c2c5] border-[#2c2e33] hover:bg-[#2c2e33] hover:border-[#4a4e55]'
                          : (inst
                              ? 'bg-[#1e3226] text-[#69db7c] border-[#2f9e44] hover:bg-[#24402f]'
                              : 'bg-[#25262b] text-[#c1c2c5] border-[#2c2e33] hover:bg-[#2c2e33] hover:border-[#4a4e55]'))}"
                  onclick={() => {
                    onSelectVersion(ver);
                    activeImg = 0;
                  }}
                  title={buzz ? "Early Access — requires Buzz" : (inst ? "Installed locally" : ver.name)}
                >
                  {#if buzz}
                    <span class="absolute right-0 top-0 bottom-0 rounded-r-full flex items-center justify-center" style="width:28%;background:linear-gradient(135deg,#f59e0b,#fbbf24,#d97706);z-index:0">
                      <svg class="w-3 h-3 shrink-0 relative z-10" viewBox="0 0 24 24" fill="currentColor" aria-label="Requires Buzz" style="filter:drop-shadow(0 1px 2px rgba(0,0,0,0.4))"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                    </span>
                  {/if}
                  <span class="relative z-10">
                    {#if inst}
                      <svg class="w-3 h-3 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                    {/if}
                    {ver.name}
                  </span>
                </button>
              {/each}
            </div>
          </div>
        {/if}

        <!-- Early Access / Buzz banner -->
        {#if isBuzzModel}
          <div class="rounded-lg bg-[#2a2410] border border-[#fab005]/40 p-3.5" data-testid="ea-banner">
            <div class="flex items-start gap-2 mb-2">
              <svg class="w-5 h-5 text-[#fab005] shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
              <div>
                <p class="text-[12px] text-[#ffd43b] leading-relaxed">
                  The creator of this {model.type || "model"} has set this version to <strong class="text-white">Early Access</strong> and as such it is only available for people who purchase it.{selectedVersion?.earlyAccessEndsAt ? ` This ` + (model.type || "model") + ` will be available for free <strong class="text-white" id="ea-countdown">{eaCountdown()}</strong> or once the donation goal is met.` : ""}
                </p>
                <a class="mt-2 inline-flex items-center gap-1 text-[11px] text-[#4dabf7] hover:text-[#74c0fc] font-medium" href="https://civitai.com/articles/6341/introducing-early-access-a-way-to-give-back-to-creators" target="_blank" rel="noopener noreferrer">
                  <svg class="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/></svg>
                  Learn more about Early Access
                </a>
              </div>
            </div>
          </div>
        {/if}

        <!-- Generation-Only notice -->
        {#if isGenerationOnly}
          <div class="rounded-lg bg-[#1a1b2e] border border-[#7c3aed]/30 p-3.5" data-testid="genonly-banner">
            <div class="flex items-start gap-2">
              <svg class="w-5 h-5 text-[#a78bfa] shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M8 12h.01M12 12h.01M16 12h.01"/></svg>
              <div>
                <p class="text-[12px] text-[#c4b5fd] leading-relaxed">
                  The creator has set this model to <strong class="text-white">Generation-Only</strong>. There is no checkpoint file to download — this model can only be used on-site at civitai.com.
                </p>
                {#if (model as any).id}
                  <a class="mt-2 inline-flex items-center gap-1 text-[11px] text-[#4dabf7] hover:text-[#74c0fc] font-medium" href="https://civitai.com/models/{(model as any).id}" target="_blank" rel="noopener noreferrer">
                    <svg class="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/></svg>
                    Open on civitai.com
                  </a>
                {/if}
              </div>
            </div>
          </div>
        {/if}

        <!-- download -->
        {#if selectedVersion}
          <div class="rounded-lg bg-[#25262b] border border-[#2c2e33] p-4" data-testid="download-section">
            <!-- header row -->
            <div class="flex items-center justify-between mb-3">
              <h3 class="text-[16px] font-bold text-[#c1c2c5] leading-none">Download</h3>
              {#if modelFiles.length}
                <span class="text-[13px] text-[#a1a1aa]">{modelFiles.length} variant{modelFiles.length > 1 ? "s" : ""} available</span>
              {/if}
            </div>

            <!-- variant rows -->
            {#if modelFiles.length > 0}
              <div class="space-y-1.5 mb-3">
                {#each modelFiles as file (file.id)}
                  {@const fdl = selectedVersion ? fileDl(file.id, selectedVersion.id) : null}
                  {@const sc = scanState(file)}
                  <div class="rounded-lg p-2.5 flex items-center gap-3 {file.primary ? 'bg-[#17202c]' : 'bg-transparent hover:bg-[#2f2f33]'}">
                    <div class="shrink-0 w-10 h-10 rounded-lg bg-[#1e3a8a] flex items-center justify-center text-white">
                      {@render typeIcon(file.type || modelType)}
                    </div>
                    <div class="min-w-0 flex-1">
                      <div class="flex items-center gap-1.5 flex-wrap">
                        <span class="text-[14px] text-white font-medium">{file.format || "SafeTensor"}</span>
                        {#if file.fp}<span class="shrink-0 text-[10px] font-bold uppercase text-[#c1c2c5] bg-[#3f3f46] px-1.5 py-0.5 rounded">{file.fp}</span>{/if}
                        <span class="shrink-0 text-[10px] font-bold uppercase tracking-wide text-[#60a5fa] bg-[#1e3a8a]/40 border border-[#3b82f6]/30 px-1.5 py-0.5 rounded">{typeLabel(file.type || modelType)}</span>
                        {#if file.primary}
                          <span class="shrink-0 text-[10px] font-bold uppercase tracking-wide text-[#c1c2c5] bg-[#3f3f46] px-1.5 py-0.5 rounded">Best match</span>
        {/if}
                      </div>
                      <p class="text-[12px] text-[#a1a1aa] truncate mt-0.5" title={file.name}>{file.name}</p>
                      <div class="flex items-center gap-2 mt-1 flex-wrap">
                        <!-- verified/scan shield -->
                        <span class="inline-flex items-center gap-1 text-[11px] {sc.ok ? 'text-[#22c55e]' : sc.pending ? 'text-[#ffa94d]' : 'text-[#ff6b6b]'}" title={file.scannedAt ? `Scanned ${sc.when}` : 'Not scanned yet'}>
                          {#if sc.ok}
                            <svg class="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l7 3v6c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V5l7-3z"/><polyline points="9 12 11 14 15 10"/></svg>
                          {:else}
                            <svg class="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l7 3v6c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V5l7-3z"/><path d="M12 8v4M12 16h.01"/></svg>
        {/if}
                          {sc.label}
                        </span>
                        <span class="text-[10px] text-[#71717a]">{sc.when}</span>
                        {#if file.sizeType}<span class="text-[11px] text-[#71717a]">{file.sizeType}</span>{/if}
                        {#if fdl?.status === "queued" || fdl?.status === "pending"}<span class="text-[11px] text-[#60a5fa]">queued…</span>
                        {:else if fdl?.status === "completed" || isInstalled(file.id)}<span class="text-[11px] text-[#22c55e]">✓ downloaded</span>
                        {:else if fStatus(file.id) === "incomplete" || fStatus(file.id) === "corrupt"}<span class="text-[11px] text-[#ffa94d]">⚠ incomplete — re-download</span>{/if}
                        {#if fdl && (fdl.status === "failed" || fdl.status === "gone")}<span class="text-[11px] text-[#ff6b6b]" title={fdl.error}>failed</span>{/if}
                      </div>
                      {#if fdl?.status === "downloading"}
                        <div class="mt-1.5 h-1 rounded-full bg-[#3f3f46] overflow-hidden">
                          <div class="h-full bg-[#2563eb] transition-all duration-500" style="width:{fdl.progress}%"></div>
                        </div>
                        <div class="text-[10px] text-[#a1a1aa] mt-0.5">
                          {fmtSize(fdl.bytesDownloaded || 0)} / {fmtSize(fdl.bytesTotal || 0)} · {fdl.progress}%{fmtSpeed(fdl.speed || 0) ? ` · ${fmtSpeed(fdl.speed || 0)}` : ""}{fmtEta(fdl.etaSec || 0) ? ` · ETA ${fmtEta(fdl.etaSec || 0)}` : ""}
                        </div>
                      {/if}
                    </div>
                    <span class="text-[13px] text-[#a1a1aa] font-medium shrink-0">{fmtS(file.sizeKB)}</span>
                    <button
                      class="shrink-0 w-9 h-9 rounded-md flex items-center justify-center transition-colors disabled:opacity-60
                        {isInstalled(file.id) ? 'bg-[#1e3226] text-[#22c55e]' : fileNeedsApiKey(file) ? 'bg-[#3f1515] text-[#ff6b6b] hover:bg-[#dc2626] hover:text-white' : 'bg-[#3f3f46] hover:bg-[#2563eb] text-[#d4d4d8] hover:text-white'}"
                      onclick={() => download(file)}
                      disabled={isActive(fdl) || (isInstalled(file.id) && fdl?.status !== 'failed' && fdl?.status !== 'gone') || fileNeedsApiKey(file)}
                      title={isInstalled(file.id) ? "Already downloaded (healthy)" : fileNeedsApiKey(file) ? "API key required — click to open civitai.com" : `Download ${file.name}`}
                      aria-label={isInstalled(file.id) ? "Already installed" : fileNeedsApiKey(file) ? "API key required" : `Download ${file.name}`}
                    >
                      {#if isActive(fdl)}
                        <svg class="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.2-8.6"/></svg>
                      {:else if fdl?.status === "completed" || isInstalled(file.id)}
                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                      {:else}
                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/></svg>
                      {/if}
                    </button>
                  </div>
                {/each}
              </div>
            {/if}

            <!-- primary download button -->
            {#if isBuzzModel}
              <div class="flex items-center gap-2 mb-2 px-3 py-1.5 rounded-full bg-[#2a2410] border border-[#fab005]/40 text-[#ffd43b] text-[12px] font-semibold">
                <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="currentColor"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                <span>Requires Buzz — unlock on civitai.com</span>
              </div>
            {/if}
            <button
              class="w-full py-2.5 rounded text-[14px] font-semibold text-white active:scale-[0.99] transition-all flex items-center justify-center gap-2 disabled:opacity-80 border
                {primaryDl?.status === 'completed' || isInstalled(primaryFile?.id) ? 'bg-[#2f9e44] border-[#37b24d] hover:bg-[#2b8a3e]' : buzzLocked ? 'bg-[#3f3f46] border-[#52525b]' : anyFileNeedsApiKey ? 'bg-[#5c1515] border-[#dc2626] hover:bg-[#7f1d1d]' : 'bg-[#1d4ed8] border-[#2563eb] hover:bg-[#1a44c2]'}"
              onclick={downloadPrimary}
              disabled={isActive(primaryDl) || modelFiles.length === 0 || buzzLocked || (isInstalled(primaryFile?.id) && primaryDl?.status !== "failed" && primaryDl?.status !== "gone")}
              data-testid="download-btn"
            >
              {#if primaryDl?.status === "queued" || primaryDl?.status === "pending"}
                <svg class="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.2-8.6"/></svg>
                <span>Queued…</span>
              {:else if primaryDl?.status === "downloading"}
                <svg class="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.2-8.6"/></svg>
                <span>Downloading… {primaryDl.progress}%</span>
              {:else if primaryDl?.status === "completed" || isInstalled(primaryFile?.id)}
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                <span>Installed</span>
              {:else if buzzLocked}
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="0"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 018 0v4" fill="none" stroke="currentColor" stroke-width="2"/></svg>
                <span class="tracking-wide">Buy on civitai.com</span>
              {:else if anyFileNeedsApiKey}
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="0"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 018 0v4" fill="none" stroke="currentColor" stroke-width="2"/></svg>
                <span class="tracking-wide">API key required</span>
              {:else}
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/></svg>
                <span class="tracking-wide">Download{primaryFile && primaryFile.sizeKB ? ` (${fmtS(primaryFile.sizeKB)})` : ""}</span>
              {/if}
            </button>
            {#if primaryDl?.status === "downloading"}
              <div class="mt-2 h-1.5 rounded-full bg-[#3f3f46] overflow-hidden">
                <div class="h-full bg-[#2563eb] transition-all duration-500" style="width:{primaryDl.progress}%"></div>
              </div>
              <div class="flex justify-between mt-1 text-[10px] text-[#a1a1aa]">
                <span>{fmtSize(primaryDl.bytesDownloaded || 0)} / {fmtSize(primaryDl.bytesTotal || 0)}</span>
                <span>{primaryDl.progress}%</span>
              </div>
            {/if}
            {#if primaryDl && (primaryDl.status === "failed" || primaryDl.status === "gone")}
              <p class="text-[11px] text-[#ff6b6b] mt-1.5 text-center">{primaryDl.error || "Download failed"}</p>
            {/if}
            {#if activeCount > 0 && totalSpeed > 0}
              <div class="flex items-center justify-center gap-1.5 mt-2 text-[11px] text-[#60a5fa]">
                <svg class="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
                <span>{activeCount} active · {fmtSpeed(totalSpeed)} total</span>
              </div>
            {/if}
            {#if modelType}
              <p class="text-[11px] text-[#5c5f66] mt-1.5 text-center">→ models/{DIR_MAP[modelType] || "Stable-diffusion"}</p>
            {/if}
          </div>
        {/if}

        <!-- required components / dependencies -->
        {#if componentFiles.length || selectedVersion?.dependencies?.length}
          {@const deps = (selectedVersion?.dependencies || []).filter((d) => !componentFiles.some((f) => f.name === d.name || f.id === d.fileId))}
          {@const compCount = componentFiles.length + deps.length}
          {@const compTotalKB = componentFiles.reduce((s, f) => s + (f.sizeKB || 0), 0) + deps.reduce((s, d) => s + (d.sizeKB || 0), 0)}
          {@const allCompInstalled = componentFiles.every((f) => isInstalled(f.id)) && deps.every((d) => isInstalled(d.fileId))}
          <div class="rounded-lg bg-[#25262b] border border-[#2c2e33] p-4" data-testid="dependencies">
            <div class="flex items-center gap-2 mb-1">
              <svg class="w-4 h-4 text-[#f59f00]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>
              <h3 class="text-[15px] font-bold text-white">Required Components</h3>
              <span class="text-[11px] font-bold text-[#f59f00] bg-[#f59f00]/10 border border-[#f59f00]/30 px-1.5 py-0.5 rounded">{compCount}</span>
            </div>
            <p class="text-[12px] text-[#a1a1aa] mb-3">You need these files to run this model.</p>
            <div class="space-y-1.5 mb-3">
              {#each componentFiles as file (file.id)}
                {@const cfl = selectedVersion ? fileDl(file.id, selectedVersion.id) : null}
                {@const cInst = isInstalled(file.id)}
                <div class="rounded-lg p-2.5 bg-[#17202c] flex items-center gap-3">
                  <div class="shrink-0 w-9 h-9 rounded-lg bg-[#3a2e0e] flex items-center justify-center text-[#f59f00]">
                    {@render typeIcon(file.type)}
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-1.5">
                      <span class="text-[10px] font-bold uppercase tracking-wide text-[#ffd43b] bg-[#3a2e12] border border-[#f08c00]/40 px-1.5 py-0.5 rounded">{typeLabel(file.type)}</span>
                    </div>
                    <p class="text-[13px] text-[#e5e7eb] truncate font-medium mt-0.5" title={file.name}>{file.name}</p>
                    <div class="flex items-center gap-2 mt-0.5">
                      <span class="text-[10px] text-[#71717a]">→ models/{fileTargetDir(file)}</span>
                      {#if cfl?.status === "queued" || cfl?.status === "pending"}<span class="text-[10px] text-[#f59f00]">queued…</span>
                      {:else if cfl?.status === "completed" || cInst}<span class="text-[10px] text-[#22c55e]">✓ downloaded</span>
                      {:else if fStatus(file.id) === "incomplete" || fStatus(file.id) === "corrupt"}<span class="text-[10px] text-[#ffa94d]">⚠ incomplete — re-download</span>{/if}
                      {#if cfl && (cfl.status === "failed" || cfl.status === "gone")}<span class="text-[10px] text-[#ff6b6b]" title={cfl.error}>failed</span>{/if}
                    </div>
                    {#if cfl?.status === "downloading"}
                      <div class="mt-1.5 h-1 rounded-full bg-[#3f3f46] overflow-hidden">
                        <div class="h-full bg-[#f59f00] transition-all duration-500" style="width:{cfl.progress}%"></div>
                      </div>
                      <div class="text-[10px] text-[#a1a1aa] mt-0.5">
                        {fmtSize(cfl.bytesDownloaded || 0)} / {fmtSize(cfl.bytesTotal || 0)} · {cfl.progress}%{fmtSpeed(cfl.speed || 0) ? ` · ${fmtSpeed(cfl.speed || 0)}` : ""}{fmtEta(cfl.etaSec || 0) ? ` · ETA ${fmtEta(cfl.etaSec || 0)}` : ""}
                      </div>
                    {/if}
                  </div>
                  <span class="text-[12px] text-[#a1a1aa] font-medium shrink-0">{fmtS(file.sizeKB)}</span>
                  <button
                    class="shrink-0 w-9 h-9 rounded-md flex items-center justify-center transition-colors disabled:opacity-60
                      {(cfl?.status === 'completed' || cInst) ? 'bg-[#1e3226] text-[#22c55e]' : 'bg-[#3f3f46] hover:bg-[#f08c00] text-[#d4d4d8] hover:text-white'}"
                    onclick={() => download(file)}
                    disabled={isActive(cfl) || (cInst && cfl?.status !== 'failed' && cfl?.status !== 'gone')}
                    title={cInst ? "Already downloaded (healthy)" : `Download ${file.name}`}
                    aria-label={`Download ${file.name}`}
                  >
                    {#if isActive(cfl)}
                      <svg class="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.2-8.6"/></svg>
                    {:else if cfl?.status === "completed" || cInst}
                      <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                    {:else}
                      <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/></svg>
                    {/if}
                  </button>
                </div>
              {/each}
              {#each deps as dep (dep.versionId + '-' + (dep.fileId ?? '0'))}
                {@const ddl = fileDl(dep.fileId ?? -1, dep.versionId)}
                {@const dInst = isInstalled(dep.fileId)}
                <div class="rounded-lg p-2.5 bg-[#17202c] flex items-center gap-3">
                  <div class="shrink-0 w-9 h-9 rounded-lg bg-[#3a2e0e] flex items-center justify-center text-[#f59f00]">
                    {@render typeIcon(dep.type)}
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-1.5">
                      <span class="text-[10px] font-bold uppercase tracking-wide text-[#ffd43b] bg-[#3a2e12] border border-[#f08c00]/40 px-1.5 py-0.5 rounded">{typeLabel(dep.type)}</span>
                      {#if dep.required}<span class="text-[10px] text-[#ff8787]">required</span>{/if}
                    </div>
                    <p class="text-[13px] text-[#e5e7eb] truncate font-medium mt-0.5" title={dep.name}>{dep.name}</p>
                    <div class="flex items-center gap-2 mt-0.5">
                      <span class="text-[10px] text-[#71717a]">→ models/{depDir(dep)}</span>
                      {#if ddl?.status === "queued" || ddl?.status === "pending"}<span class="text-[10px] text-[#f59f00]">queued…</span>
                      {:else if ddl?.status === "completed" || dInst}<span class="text-[10px] text-[#22c55e]">✓ downloaded</span>
                      {:else if fStatus(dep.fileId) === "incomplete" || fStatus(dep.fileId) === "corrupt"}<span class="text-[10px] text-[#ffa94d]">⚠ incomplete — re-download</span>{/if}
                      {#if ddl && (ddl.status === "failed" || ddl.status === "gone")}<span class="text-[10px] text-[#ff6b6b]" title={ddl.error}>failed</span>{/if}
                    </div>
                    {#if ddl?.status === "downloading"}
                      <div class="mt-1.5 h-1 rounded-full bg-[#3f3f46] overflow-hidden">
                        <div class="h-full bg-[#f59f00] transition-all duration-500" style="width:{ddl.progress}%"></div>
                      </div>
                      <div class="text-[10px] text-[#a1a1aa] mt-0.5">
                        {fmtSize(ddl.bytesDownloaded || 0)} / {fmtSize(ddl.bytesTotal || 0)} · {ddl.progress}%{fmtSpeed(ddl.speed || 0) ? ` · ${fmtSpeed(ddl.speed || 0)}` : ""}{fmtEta(ddl.etaSec || 0) ? ` · ETA ${fmtEta(ddl.etaSec || 0)}` : ""}
                      </div>
                    {/if}
                  </div>
                  <span class="text-[12px] text-[#a1a1aa] font-medium shrink-0">{fmtS(dep.sizeKB)}</span>
                  <button
                    class="shrink-0 w-9 h-9 rounded-md flex items-center justify-center transition-colors disabled:opacity-60
                      {(ddl?.status === 'completed' || dInst) ? 'bg-[#1e3226] text-[#22c55e]' : 'bg-[#3f3f46] hover:bg-[#f08c00] text-[#d4d4d8] hover:text-white'}"
                    onclick={() => downloadDep(dep)}
                    disabled={isActive(ddl) || (dInst && ddl?.status !== 'failed' && ddl?.status !== 'gone')}
                    title={dInst ? "Already downloaded (healthy)" : `Download ${dep.name}`}
                    aria-label={`Download ${dep.name}`}
                  >
                    {#if isActive(ddl)}
                      <svg class="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.2-8.6"/></svg>
                    {:else if ddl?.status === "completed" || dInst}
                      <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                    {:else}
                      <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/></svg>
                    {/if}
                  </button>
                </div>
              {/each}
            </div>
            {#if compCount > 1}
              {#if allCompInstalled}
                <div class="w-full py-2.5 rounded-lg text-[13px] font-semibold text-[#22c55e] bg-[#1e3226] border border-[#2f9e44]/40 flex items-center justify-center gap-2">
                  <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l7 3v6c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V5l7-3z"/><polyline points="9 12 11 14 15 10"/></svg>
                  <span>All components installed</span>
                </div>
              {:else}
                <button
                  class="w-full py-2.5 rounded-lg text-[13px] font-semibold text-white bg-[#f08c00] hover:bg-[#e07e00] active:scale-[0.99] transition-all flex items-center justify-center gap-2"
                  onclick={downloadAllDeps}
                  aria-label="Download all components"
                >
                  <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/></svg>
                  <span>Download All Components ({fmtS(compTotalKB)})</span>
                </button>
              {/if}
            {/if}
          </div>
        {/if}

        <!-- License -->
        {#if selectedVersion?.allowCommercialUse !== undefined || selectedVersion?.allowDerivatives !== undefined || selectedVersion?.allowNoCredit !== undefined}
          {@const cUse = selectedVersion?.allowCommercialUse}
          {@const deriv = selectedVersion?.allowDerivatives}
          {@const noCredit = selectedVersion?.allowNoCredit}
          <div class="rounded-lg bg-[#25262b] border border-[#2c2e33] p-4">
            <h3 class="text-[11px] font-semibold text-[#909296] uppercase tracking-[0.1em] mb-2.5">License</h3>
            <div class="flex flex-wrap gap-1.5">
              {#if cUse === true}<span class="text-[10px] font-bold uppercase tracking-wide text-[#22c55e] bg-[#1e3226] border border-[#2f9e44]/40 px-2 py-1 rounded">Commercial</span>{:else if cUse === false}<span class="text-[10px] font-bold uppercase tracking-wide text-[#ff6b6b] bg-[#2c1a1a] border border-[#dc2626]/40 px-2 py-1 rounded">No Commercial Use</span>{:else if typeof cUse === 'string' && cUse}<span class="text-[10px] font-bold uppercase tracking-wide text-[#22c55e] bg-[#1e3226] border border-[#2f9e44]/40 px-2 py-1 rounded">Commercial ({cUse})</span>{/if}
              {#if deriv === true}<span class="text-[10px] font-bold uppercase tracking-wide text-[#22c55e] bg-[#1e3226] border border-[#2f9e44]/40 px-2 py-1 rounded">Derivatives</span>{:else if deriv === false}<span class="text-[10px] font-bold uppercase tracking-wide text-[#ff6b6b] bg-[#2c1a1a] border border-[#dc2626]/40 px-2 py-1 rounded">No Derivatives</span>{/if}
              {#if noCredit === false}<span class="text-[10px] font-bold uppercase tracking-wide text-[#ffd43b] bg-[#2a2410] border border-[#fab005]/40 px-2 py-1 rounded">Credit Required</span>{/if}
              {#if selectedVersion?.allowDifferentLicense === true}<span class="text-[10px] font-bold uppercase tracking-wide text-[#ffa94d] bg-[#2a1e14] border border-[#f08c00]/40 px-2 py-1 rounded">Mixed License Terms</span>{/if}
            </div>
          </div>
        {/if}

        <!-- details table -->
        <div>
          <h3 class="text-[11px] font-semibold text-[#909296] uppercase tracking-[0.1em] mb-2">Details</h3>
          <div class="rounded border border-[#2c2e33] overflow-hidden text-[13px]">
            {#if modelType}
              <div class="flex justify-between px-3 py-2 bg-[#25262b] border-b border-[#2c2e33]">
                <span class="text-[#909296]">Type</span><span class="text-[#c1c2c5] font-medium">{modelType}</span>
              </div>
            {/if}
            {#if selectedVersion?.baseModel}
              <div class="flex justify-between px-3 py-2 border-b border-[#2c2e33]">
                <span class="text-[#909296]">Base Model</span><span class="text-[#4dabf7] font-medium">{selectedVersion.baseModel}</span>
              </div>
            {/if}
            {#if published}
              <div class="flex justify-between px-3 py-2 bg-[#25262b] border-b border-[#2c2e33]">
                <span class="text-[#909296]">Published</span><span class="text-[#c1c2c5]">{published}</span>
              </div>
            {/if}
            <div class="flex justify-between px-3 py-2 border-b border-[#2c2e33]">
              <span class="text-[#909296]">Downloads</span><span class="text-[#c1c2c5]">{fmtCount((model.stats || {}).downloadCount || 0)}</span>
            </div>
            {#if review}
              <div class="flex justify-between px-3 py-2 border-b border-[#2c2e33] gap-2">
                <span class="text-[#909296]">Reviews</span>
                <span class="{review.positive ? 'text-[#51cf66]' : 'text-[#ffa94d]'} font-medium text-right">{review.label} <span class="text-[#909296] font-normal">({fmtCount(review.total)})</span></span>
              </div>
            {/if}
            {#if hashStr}
              <div class="flex justify-between items-center px-3 py-2 bg-[#25262b] gap-2">
                <span class="text-[#909296]">Hash</span>
                <button
                  class="inline-flex items-center gap-1.5 min-w-0 text-[#c1c2c5] font-mono hover:text-[#4dabf7] transition-colors"
                  onclick={() => copyWord(hashStr)}
                  title="Click to copy hash"
                >
                  <span class="truncate">{copied === hashStr ? "copied!" : hashStr}</span>
                  <svg class="w-[18px] h-[18px] shrink-0 {copied === hashStr ? 'text-[#51cf66]' : 'text-[#5c5f66]'}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
                </button>
              </div>
            {/if}
            {#if selectedVersion?.clipSkip != null}
              <div class="flex justify-between px-3 py-2 border-b border-[#2c2e33]">
                <span class="text-[#909296]">Clip Skip</span><span class="text-[#c1c2c5] font-medium">{selectedVersion.clipSkip}</span>
              </div>
            {/if}
            {#if selectedVersion?.epochs != null}
              <div class="flex justify-between px-3 py-2 bg-[#25262b] border-b border-[#2c2e33]">
                <span class="text-[#909296]">Epochs</span><span class="text-[#c1c2c5] font-medium">{selectedVersion.epochs}</span>
              </div>
            {/if}
            {#if selectedVersion?.steps != null}
              <div class="flex justify-between px-3 py-2 border-b border-[#2c2e33]">
                <span class="text-[#909296]">Steps</span><span class="text-[#c1c2c5] font-medium">{fmtCount(selectedVersion.steps!)}</span>
              </div>
            {/if}
            {#if selectedVersion?.tensorType}
              <div class="flex justify-between px-3 py-2 bg-[#25262b] border-b border-[#2c2e33]">
                <span class="text-[#909296]">Tensor Type</span><span class="text-[#c1c2c5] font-medium">{selectedVersion.tensorType}</span>
              </div>
            {/if}
            {#if selectedVersion?.modelSize}
              <div class="flex justify-between px-3 py-2 border-b border-[#2c2e33]">
                <span class="text-[#909296]">Model Size</span><span class="text-[#c1c2c5] font-medium">{selectedVersion.modelSize}</span>
              </div>
            {/if}
            {#if (selectedVersion as any)?.tensorCount != null}
              <div class="flex justify-between px-3 py-2 bg-[#25262b]">
                <span class="text-[#909296]">Tensors</span><span class="text-[#c1c2c5] font-medium">{fmtCount((selectedVersion as any).tensorCount)}</span>
              </div>
            {/if}
          </div>
        </div>

        <!-- trigger words -->
        {#if selectedVersion?.trainedWords?.length}
          <div>
            <h3 class="text-[11px] font-semibold text-[#909296] uppercase tracking-[0.1em] mb-2">Trigger Words</h3>
            <div class="flex flex-wrap gap-1.5">
              {#each selectedVersion.trainedWords as w (w)}
                <button
                  class="px-2.5 py-1 bg-[#25262b] rounded-lg text-[12px] font-mono border transition-colors
                    {copied === w ? 'text-[#51cf66] border-[#51cf66]' : 'text-[#4dabf7] border-[#2c2e33] hover:bg-[#2c2e33] hover:border-[#4a4e55]'}"
                  onclick={() => copyWord(w)}
                  title="Click to copy"
                >
                  {copied === w ? "copied!" : w}
                </button>
              {/each}
            </div>
          </div>
        {/if}

        <!-- About this version -->
        {#if selectedVersion?.description}
          <div class="rounded-lg bg-[#25262b] border border-[#2c2e33] overflow-hidden">
            <button
              class="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-[#2c2e33] transition-colors !border-b border-[#2c2e33]"
              onclick={(e) => {
                const btn = e.currentTarget;
                const content = btn.nextElementSibling as HTMLElement;
                const open = !btn.classList.contains("collapsed");
                if (open) {
                  content.style.maxHeight = "0px";
                  btn.classList.remove("!border-b");
                  btn.classList.add("collapsed");
                } else {
                  content.style.maxHeight = content.scrollHeight + "px";
                  btn.classList.add("!border-b");
                  btn.classList.remove("collapsed");
                }
              }}
            >
              <span class="text-[13px] font-semibold text-[#c1c2c5]">About this version{selectedVersion?.name ? ` — ${selectedVersion.name}` : ""}</span>
              <svg class="w-4 h-4 text-[#5c5f66] transition-transform duration-200 expand-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>
            </button>
            <div class="overflow-hidden transition-all duration-200" style="max-height:2000px">
              <div class="px-4 py-3 text-[13px] leading-relaxed text-[#a1a1aa]
                [&_a]:text-[#4dabf7] [&_a]:underline
                [&_em]:text-[#c1c2c5]
                [&_strong]:text-[#c1c2c5] [&_strong]:font-semibold
                [&_code]:text-[#4dabf7] [&_code]:bg-[#1a1b1e] [&_code]:px-1 [&_code]:rounded
                [&_ul]:pl-4 [&_ol]:pl-4 [&_li]:mb-1
                [&_p]:mb-2">
                {@html sanitizeHtml(selectedVersion.description)}
              </div>
            </div>
          </div>
        {/if}

        <!-- tags -->
        {#if modelTags.length}
          <div>
            <h3 class="text-[11px] font-semibold text-[#909296] uppercase tracking-[0.1em] mb-2">Tags</h3>
            <div class="flex flex-wrap gap-1.5" data-testid="tags">
              {#each modelTags as t (t)}
                <button
                  class="px-2.5 py-1 bg-[#25262b] rounded-full text-[11px] text-[#9da4ae] border border-[#2c2e33] uppercase tracking-wide hover:bg-[#2c2e33] hover:text-[#c1c2c5] hover:border-[#4a4e55] cursor-pointer transition-colors"
                  onclick={() => searchByTag(t)}
                  title={`Search Civitai for "${t}"`}
                >{t}</button>
              {/each}
            </div>
          </div>
        {/if}

        <!-- creator card -->
        {#if model.creator?.username}
          <CreatorCard {model} {selectedVersion} />
        {/if}

        <!-- recent comments -->
        {#if comments.length > 0}
          <div class="rounded-lg bg-[#25262b] border border-[#2c2e33] overflow-hidden">
            <h3 class="text-[11px] font-semibold text-[#909296] uppercase tracking-[0.1em] px-4 pt-3 pb-2">Discussion</h3>
            {#each comments.slice(0, 4) as c (c.id)}
              <div class="px-4 py-2.5 border-t border-[#2c2e33]">
                <div class="flex items-center gap-2 mb-1">
                  {#if c.user?.image}
                    <img class="w-5 h-5 rounded-full object-cover" src={c.user.image} alt="" />
                  {:else}
                    <div class="w-5 h-5 rounded-full bg-[#373a40] flex items-center justify-center text-[10px] text-[#9da4ae]">{c.user?.username?.charAt(0)?.toUpperCase() || "?"}</div>
                  {/if}
                  <span class="text-[12px] font-medium text-[#c1c2c5]">{c.user?.username || "Unknown"}</span>
                  <span class="text-[10px] text-[#5c5f66] ml-auto">{c.createdAt ? new Date(c.createdAt).toLocaleDateString() : ""}</span>
                </div>
                <p class="text-[12px] text-[#a1a1aa] leading-relaxed line-clamp-3">{@html sanitizeHtml(c.content)}</p>
              </div>
            {/each}
            {#if commentsCursor}
              <button
                class="block w-full text-center text-[12px] text-[#4dabf7] hover:text-[#74c0fc] py-2.5 border-t border-[#2c2e33] transition-colors cursor-pointer"
                onclick={loadMoreComments}
                disabled={commentsLoading}
              >{commentsLoading ? "Loading…" : "Load more comments"}</button>
            {/if}
            <a
              class="block text-center text-[12px] text-[#909296] hover:text-[#c1c2c5] py-2 border-t border-[#2c2e33] no-underline transition-colors"
              href={`https://civitai.com/models/${model.id}`}
              target="_blank"
              rel="noopener noreferrer"
            >View on Civitai</a>
          </div>
        {/if}
      </div>
    </aside>
    </div>
  </div>
</div>

{#if showLb}
  <PopupLightbox images={galleryImages} initialIndex={lbIdx} onclose={() => (showLb = false)} />
{/if}

<style>
  .popup-backdrop {
    padding: 3vh 3vw;
    background:
      radial-gradient(circle at 18% 10%, rgb(41 96 155 / 0.2), transparent 34%),
      radial-gradient(circle at 82% 92%, rgb(166 109 57 / 0.12), transparent 32%),
      rgb(3 6 12 / 0.86);
    backdrop-filter: blur(18px) saturate(0.8);
  }

  .popup-canvas {
    border: 1px solid rgb(148 163 184 / 0.18);
    border-radius: 22px;
    background:
      linear-gradient(145deg, rgb(25 31 42 / 0.98), rgb(11 15 23 / 0.99) 58%),
      #0b0f17;
    box-shadow: 0 36px 100px rgb(0 0 0 / 0.62), 0 0 0 1px rgb(255 255 255 / 0.025) inset;
  }

  .popup-topbar {
    border-bottom: 1px solid rgb(148 163 184 / 0.14);
    background: rgb(15 20 29 / 0.82);
    backdrop-filter: blur(18px);
  }

  .popup-mark {
    width: 28px;
    height: 2px;
    border-radius: 999px;
    background: linear-gradient(90deg, #53b7ff, #d8ad78);
    box-shadow: 0 0 18px rgb(83 183 255 / 0.5);
  }

  .popup-close {
    border: 1px solid rgb(148 163 184 / 0.16);
    background: rgb(255 255 255 / 0.045);
  }

  .popup-close:hover {
    border-color: rgb(83 183 255 / 0.42);
    background: rgb(83 183 255 / 0.13);
    transform: rotate(4deg);
  }

  .popup-workspace {
    background-image: linear-gradient(rgb(255 255 255 / 0.014) 1px, transparent 1px);
    background-size: 100% 56px;
  }

  .popup-media-column {
    scrollbar-color: rgb(93 106 125 / 0.58) transparent;
  }

  .popup-viewer {
    background:
      radial-gradient(circle at 50% 0%, rgb(63 122 173 / 0.12), transparent 46%),
      linear-gradient(180deg, rgb(255 255 255 / 0.018), transparent);
  }

  .popup-description {
    position: relative;
    border-top: 1px solid rgb(148 163 184 / 0.12);
    background: rgb(10 14 21 / 0.58);
  }

  .popup-description::before {
    position: absolute;
    top: -1px;
    left: 32px;
    width: 86px;
    height: 1px;
    content: "";
    background: linear-gradient(90deg, #53b7ff, transparent);
  }

  .popup-inspector {
    border-left: 1px solid rgb(148 163 184 / 0.14);
    background: rgb(12 16 24 / 0.88);
    box-shadow: -22px 0 60px rgb(0 0 0 / 0.18);
    scrollbar-color: rgb(93 106 125 / 0.58) transparent;
  }

  .popup-inspector h1 {
    color: #f2f5f9;
    font-size: clamp(28px, 2vw, 38px);
    font-weight: 680;
    letter-spacing: -0.045em;
    text-wrap: balance;
  }

  .popup-inspector [data-testid="download-section"],
  .popup-inspector [data-testid="dependencies"],
  .popup-inspector :global(.creator-card) {
    border-color: rgb(148 163 184 / 0.15);
    border-radius: 14px;
    background: linear-gradient(145deg, rgb(37 45 58 / 0.76), rgb(23 29 40 / 0.7));
    box-shadow: 0 12px 34px rgb(0 0 0 / 0.2), 0 1px 0 rgb(255 255 255 / 0.035) inset;
  }

  .popup-inspector [data-testid="download-btn"] {
    min-height: 42px;
    border-radius: 10px;
    box-shadow: 0 8px 22px rgb(29 78 216 / 0.2);
  }

  @media (max-width: 1100px) {
    .popup-backdrop { padding: 0; }
    .popup-canvas { width: 100vw; height: 100vh; border: 0; border-radius: 0; }
    .popup-workspace { flex-direction: column; overflow-y: auto; }
    .popup-media-column { overflow: visible; }
    .popup-inspector { width: 100%; overflow: visible; border-top: 1px solid rgb(148 163 184 / 0.14); border-left: 0; }
  }
</style>
