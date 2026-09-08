<script lang="ts">
  import { onMount, onDestroy } from "svelte";
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

  let previouslyFocused: HTMLElement | null = null;
  let popupCanvasEl = $state<HTMLDivElement | null>(null);

  onMount(() => {
    previouslyFocused = document.activeElement as HTMLElement | null;
    popupCanvasEl?.focus();
  });

  onDestroy(() => {
    if (previouslyFocused?.isConnected) previouslyFocused.focus();
  });

  function handlePopupKeydown(e: KeyboardEvent) {
    if (showLb || e.defaultPrevented) return;
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    } else if (e.key === "Tab" && popupCanvasEl) {
      const focusables = Array.from(popupCanvasEl.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, summary, video[controls], [tabindex]'
      )).filter(el => el.tabIndex >= 0 && !el.hasAttribute("disabled") && el.getClientRects().length > 0);
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (!first) {
        e.preventDefault();
        popupCanvasEl.focus();
      } else if (e.shiftKey && (active === first || active === popupCanvasEl)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  // Map a component/file type (or filename) to the correct WebUI subdirectory.
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

  function isComponentType(t: string | undefined): boolean {
    const s = (t || "").toLowerCase();
    return s.includes("vae") || s.includes("encoder") || s.includes("config") || s.includes("negative") || s.includes("archive");
  }

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
    if (isActive(dl)) return;
    if (isInstalled(dep.fileId) && dl?.status !== "failed" && dl?.status !== "gone") return;
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

  async function downloadAllDeps() {
    for (const f of componentFiles) {
      await download(f);
    }
    for (const dep of selectedVersion?.dependencies || []) {
      await downloadDep(dep);
    }
  }

  function searchByTag(tag: string) {
    onClose();
    appState.setFilter("search", tag);
    appState.setFilter("modelType", [modelType]);
    (appState.filters as any).baseModel = [];
    (appState.filters as any).sort = "Most Downloaded";
    (appState.filters as any).period = "AllTime";
    appState.triggerSearch();
  }

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


<div
  class="popup-backdrop fixed inset-0 z-50 flex items-center justify-center p-0 sm:p-4 lg:p-6 backdrop-in"
  onclick={onClose}
  onkeydown={handlePopupKeydown}
  role="presentation"
  data-testid="popup-backdrop"
>
  <div
    bind:this={popupCanvasEl}
    class="popup-canvas popup-enter relative w-full lg:w-[94vw] h-full lg:h-[92vh] max-w-[1780px] overflow-hidden flex flex-col focus-visible:outline-none"
    role="dialog"
    aria-modal="true"
    tabindex="-1"
    aria-label={model.name}
    data-testid="popup"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => { e.stopPropagation(); handlePopupKeydown(e); }}
  >
    <button
      class="popup-close absolute top-3.5 right-3.5 z-40 w-10 h-10 rounded-full flex items-center justify-center text-white/80 hover:text-[#0b1018] bg-black/60 hover:bg-[var(--civ-accent,#67e8c6)] backdrop-blur-md border border-white/20 transition-all duration-200 cursor-pointer shadow-lg active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--civ-accent,#67e8c6)]"
      onclick={onClose}
      aria-label="Close dialog"
      title="Close (Esc)"
    >
      <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
    </button>

    <!-- BODY -->
    {#snippet typeIcon(t: string | undefined)}
      {@const c = typeCat(t)}
      {#if c === "vae"}
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 3v6M21 12h-6M12 21v-6M3 12h6M12 12l4.5-4.5M12 12l-4.5 4.5"/></svg>
      {:else if c === "te"}
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 5h14M12 5v14M8 19h8"/></svg>
      {:else if c === "lora"}
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h10M18 6h2M4 12h2M10 12h10M4 18h6M14 18h6"/><circle cx="16" cy="6" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="12" cy="18" r="2"/></svg>
      {:else if c === "embedding"}
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.6 13.4l-7.2 7.2a2 2 0 01-2.8 0l-7-7A2 2 0 013 12.2V5a2 2 0 012-2h7.2a2 2 0 011.4.6l7 7a2 2 0 010 2.8z"/><circle cx="7.5" cy="7.5" r="1.3" fill="currentColor"/></svg>
      {:else if c === "controlnet"}
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="12" cy="18" r="2"/><path d="M7 6h10M6 8l5 8M18 8l-5 8"/></svg>
      {:else if c === "config"}
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.9l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.9-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 01-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.9.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.9 1.7 1.7 0 00-1.5-1H3a2 2 0 010-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.9l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.9.3H9a1.7 1.7 0 001-1.5V3a2 2 0 014 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.9-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.9V9a1.7 1.7 0 001.5 1H21a2 2 0 010 4h-.1a1.7 1.7 0 00-1.5 1z"/></svg>
      {:else if c === "checkpoint"}
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 2l9 5-9 5-9-5 9-5z"/><path d="M3 12l9 5 9-5"/><path d="M3 17l9 5 9-5"/></svg>
      {:else}
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 3v5h5M9 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5z"/></svg>
      {/if}
    {/snippet}

    <div class="popup-workspace flex-1 flex flex-col lg:flex-row overflow-hidden min-h-0">
      <!-- LEFT: enlarged viewer + carousel + description -->
      <div class="popup-media-column flex-1 flex flex-col overflow-y-auto min-w-0">
        <div class="popup-viewer pl-5 pr-5 pb-3 pt-[52px] lg:pt-5" data-testid="viewer">
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
        <div class="popup-description px-6 sm:px-8 py-8 space-y-7">
          {#snippet prose(html: string)}
            <div
              class="text-sm text-[var(--civ-ink,#ecf4fb)] leading-relaxed prose prose-invert max-w-3xl
              prose-headings:text-white prose-headings:font-bold prose-headings:mt-6 prose-headings:mb-3
              prose-a:text-[var(--civ-accent,#67e8c6)] prose-a:no-underline hover:prose-a:underline
              prose-strong:text-white prose-strong:font-semibold
              prose-p:my-3 prose-ul:my-3 prose-li:my-1
              prose-pre:bg-[var(--civ-panel-raised,#1a2636)] prose-pre:border prose-pre:border-white/10 prose-pre:rounded-xl prose-pre:text-xs
              prose-code:text-[var(--civ-accent,#67e8c6)] prose-code:bg-[var(--civ-panel-raised,#1a2636)] prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-code:text-xs prose-code:font-mono prose-code:before:content-none prose-code:after:content-none
              prose-img:rounded-2xl prose-img:my-4
              prose-hr:border-white/10"
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
            <p class="text-[var(--civ-muted,#a0b2c6)] italic text-sm">No description provided.</p>
          {/if}
        </div>

        <!-- Suggested Resources -->
        {#if suggestions.length > 0}
          <div class="flex items-center gap-3 px-6 sm:px-8 pt-6 pb-1">
            <div class="flex-1" style="height:2px;background:linear-gradient(90deg,transparent,rgba(103,232,198,0.4) 15%,rgba(103,232,198,0.4) 85%,transparent);border-radius:1px"></div>
          </div>
          <div class="px-6 sm:px-8 pb-4">
            <h3 class="text-xs font-bold text-[var(--civ-muted,#a0b2c6)] uppercase tracking-wider mb-3">Suggested Resources</h3>
            <div class="flex gap-3.5 overflow-x-auto pb-2 civ-hscroll">
              {#each suggestions as s (s.id)}
                <a
                  href={`https://civitai.com/models/${s.id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  class="shrink-0 w-[180px] rounded-xl overflow-hidden bg-[var(--civ-panel-raised,#1a2636)] border border-[var(--civ-border,rgba(42,58,78,0.6))] hover:border-[var(--civ-accent,#67e8c6)] hover:scale-[1.02] transition-all no-underline shadow-md"
                >
                  <div class="aspect-[3/4] bg-[#0b1018] relative">
                    {#if s.images?.[0]?.url}
                      <img class="absolute inset-0 w-full h-full object-cover object-top" src={imgSrc(s.images[0], 400)} alt="" loading="lazy" />
                    {/if}
                    <div class="absolute bottom-0 left-0 right-0 p-3 bg-gradient-to-t from-black/95 via-black/60 to-transparent">
                      <p class="text-xs text-white font-bold leading-tight line-clamp-2 mb-1">{s.name}</p>
                      <span class="text-[10px] text-[var(--civ-accent,#67e8c6)] uppercase font-bold tracking-wider">{s.type}</span>
                    </div>
                  </div>
                </a>
              {/each}
            </div>
          </div>
        {/if}

        <!-- user image gallery -->
        {#if galleryImages.length > 0}
          <div class="flex items-center gap-3 px-6 sm:px-8 pt-6 pb-1">
            <div class="flex-1" style="height:2px;background:linear-gradient(90deg,transparent,rgba(103,232,198,0.4) 15%,rgba(103,232,198,0.4) 85%,transparent);border-radius:1px"></div>
          </div>
          <div class="px-6 sm:px-8 py-4">
            <h3 class="text-xs font-bold text-[var(--civ-muted,#a0b2c6)] uppercase tracking-wider mb-3">Gallery</h3>
            <div class="grid gap-2.5" style="grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));">
              {#each galleryImages.slice(0, galleryVisible) as img, i (img.url || i)}
                <button
                  class="aspect-square rounded-xl overflow-hidden bg-[var(--civ-panel-raised,#1a2636)] border border-[var(--civ-border,rgba(42,58,78,0.6))] cursor-pointer hover:border-[var(--civ-accent,#67e8c6)] hover:scale-105 transition-all shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--civ-accent,#67e8c6)]"
                  onclick={() => { lbIdx = i; showLb = true; }}
                  aria-label={`Open gallery image ${i + 1}`}
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
      <aside class="popup-inspector w-full lg:w-[440px] shrink-0 flex flex-col overflow-y-auto" data-testid="right-col">
        <div class="p-6 flex flex-col gap-6">
          <!-- model name + stats -->
          <div>
            <h1 class="text-3xl lg:text-4xl font-extrabold text-[var(--civ-ink,#ecf4fb)] leading-tight tracking-tight">{model.name}</h1>
            {#if selectedVersion?.name}
              <p class="mt-1.5 text-base font-bold text-[var(--civ-accent,#67e8c6)]">{selectedVersion.name}</p>
            {/if}
            <div class="flex items-center gap-3.5 mt-3 text-sm text-[var(--civ-ink,#ecf4fb)]">
              <span class="inline-flex items-center gap-1.5 font-semibold text-[var(--civ-accent,#67e8c6)]" title="Downloads">
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                {fmtCount((model.stats || {}).downloadCount || 0)}
              </span>
              <span class="inline-flex items-center gap-1.5 font-semibold text-[var(--civ-warm,#ffc982)]" title="Likes">
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3zM7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3"/></svg>
                {fmtCount((model.stats || {}).thumbsUpCount || 0)}
              </span>
              {#if (model.stats || {}).rating}
                <span class="inline-flex items-center gap-1.5 text-amber-300 font-bold">
                  <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
                  {((model.stats || {}).rating ?? 0).toFixed(1)}
                </span>
              {/if}
            </div>
            {#if ((model.stats || {}).ratingCount || 0) > 0}
              <div class="mt-3 flex items-center gap-2.5">
                <div class="flex-1 h-2 rounded-full bg-[var(--civ-panel-raised,#1a2636)] overflow-hidden border border-white/10">
                  <div class="h-full bg-gradient-to-r from-amber-400 to-amber-300 rounded-full transition-all" style="width:{Math.min(100, (((model.stats || {}).rating ?? 0) / 5) * 100)}%"></div>
                </div>
                <span class="text-xs font-semibold text-[var(--civ-muted,#a0b2c6)] shrink-0">{fmtCount((model.stats || {}).ratingCount || 0)} reviews</span>
              </div>
            {/if}
            <!-- creator -->
            <div class="flex items-center gap-2.5 mt-3.5">
              {#if model.creator?.image}
                <img class="w-8 h-8 rounded-full object-cover border border-white/20 shadow-sm" src={model.creator.image} alt="" />
              {:else}
                <div class="w-8 h-8 rounded-full bg-[var(--civ-panel-raised,#1a2636)] flex items-center justify-center text-xs font-bold text-[var(--civ-muted,#a0b2c6)] border border-white/20">{model.creator?.username?.charAt(0)?.toUpperCase() || "?"}</div>
              {/if}
              <span class="text-sm font-semibold text-[var(--civ-ink,#ecf4fb)]">{model.creator?.username || "Unknown"}</span>
            </div>

            <!-- type / base model badges -->
            <div class="flex flex-wrap items-center gap-1.5 mt-3.5">
              {#if modelType}
                <span class="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-[var(--civ-accent,#67e8c6)] bg-[var(--civ-accent,#67e8c6)]/15 border border-[var(--civ-accent,#67e8c6)]/30 px-2.5 py-1 rounded-lg">
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16M4 12h16M4 17h10"/></svg>
                  {modelType}
                </span>
              {/if}
              {#if selectedVersion?.baseModel}
                <span class="text-[11px] font-bold uppercase tracking-wider text-[var(--civ-violet,#b7a4ff)] bg-[var(--civ-violet,#b7a4ff)]/15 border border-[var(--civ-violet,#b7a4ff)]/30 px-2.5 py-1 rounded-lg">{selectedVersion.baseModel}</span>
              {/if}
              {#if model.nsfw}
                <span class="text-[11px] font-bold uppercase tracking-wider text-rose-400 bg-rose-500/15 border border-rose-500/30 px-2.5 py-1 rounded-lg">NSFW</span>
              {/if}
            </div>
          </div>

          <!-- version selector -->
          {#if versions.length > 0}
            <div>
              <h3 class="text-xs font-bold text-[var(--civ-muted,#a0b2c6)] uppercase tracking-wider mb-2.5">Versions</h3>
              <div class="flex flex-wrap gap-2" data-testid="versions">
                {#each versions as ver (ver.id)}
                  {@const inst = installedSet.has(ver.id)}
                  {@const buzz = (ver as any).availability === 'EarlyAccess' || (ver as any).buzzCost > 0}
                  <button
                    style="padding:5px 12px; position:relative; overflow:hidden"
                    class="rounded-full text-xs font-bold leading-tight transition-all duration-200 border inline-flex items-center gap-1.5 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--civ-accent,#67e8c6)]
                      {selectedVersion?.id === ver.id
                        ? 'bg-[var(--civ-accent,#67e8c6)] text-[#0b1018] border-[var(--civ-accent,#67e8c6)] shadow-[0_0_14px_rgba(103,232,198,0.4)] scale-[1.02]'
                        : (buzz
                            ? 'bg-[var(--civ-panel-raised,#1a2636)] text-[var(--civ-ink,#ecf4fb)] border-amber-500/40 hover:bg-amber-500/20'
                            : (inst
                                ? 'bg-emerald-950/40 text-emerald-300 border-emerald-500/40 hover:bg-emerald-900/40'
                                : 'bg-[var(--civ-panel-raised,#1a2636)] text-[var(--civ-ink,#ecf4fb)] border-[var(--civ-border,rgba(42,58,78,0.6))] hover:border-white/30'))}"
                    onclick={() => {
                      onSelectVersion(ver);
                      activeImg = 0;
                    }}
                    title={buzz ? "Early Access — requires Buzz" : (inst ? "Installed locally" : ver.name)}
                    aria-label={`Select version ${ver.name}`}
                  >
                    {#if buzz}
                      <span class="absolute right-0 top-0 bottom-0 rounded-r-full flex items-center justify-center px-1" style="background:linear-gradient(135deg,#f59e0b,#fbbf24,#d97706);z-index:0">
                        <svg class="w-3 h-3 shrink-0 relative z-10 text-[#0b1018]" viewBox="0 0 24 24" fill="currentColor"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                      </span>
                    {/if}
                    <span class="relative z-10 inline-flex items-center gap-1">
                      {#if inst}
                        <svg class="w-3.5 h-3.5 shrink-0 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
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
            <div class="rounded-2xl bg-amber-950/40 border border-amber-500/40 p-4 shadow-md" data-testid="ea-banner">
              <div class="flex items-start gap-3">
                <svg class="w-5 h-5 text-amber-400 shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                <div>
                  <p class="text-xs text-amber-200 leading-relaxed">
                    The creator of this {model.type || "model"} has set this version to <strong class="text-white">Early Access</strong> and as such it is only available for people who purchase it.{selectedVersion?.earlyAccessEndsAt ? ` This ` + (model.type || "model") + ` will be available for free <strong class="text-white" id="ea-countdown">{eaCountdown()}</strong> or once the donation goal is met.` : ""}
                  </p>
                  <a class="mt-2 inline-flex items-center gap-1 text-xs text-[var(--civ-accent,#67e8c6)] hover:underline font-semibold" href="https://civitai.com/articles/6341/introducing-early-access-a-way-to-give-back-to-creators" target="_blank" rel="noopener noreferrer">
                    <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/></svg>
                    Learn more about Early Access
                  </a>
                </div>
              </div>
            </div>
          {/if}

          <!-- Generation-Only notice -->
          {#if isGenerationOnly}
            <div class="rounded-2xl bg-purple-950/40 border border-purple-500/40 p-4 shadow-md" data-testid="genonly-banner">
              <div class="flex items-start gap-3">
                <svg class="w-5 h-5 text-purple-400 shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M8 12h.01M12 12h.01M16 12h.01"/></svg>
                <div>
                  <p class="text-xs text-purple-200 leading-relaxed">
                    The creator has set this model to <strong class="text-white">Generation-Only</strong>. There is no checkpoint file to download — this model can only be used on-site at civitai.com.
                  </p>
                  {#if (model as any).id}
                    <a class="mt-2 inline-flex items-center gap-1 text-xs text-[var(--civ-accent,#67e8c6)] hover:underline font-semibold" href="https://civitai.com/models/{(model as any).id}" target="_blank" rel="noopener noreferrer">
                      <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/></svg>
                      Open on civitai.com
                    </a>
                  {/if}
                </div>
              </div>
            </div>
          {/if}

          <!-- download section -->
          {#if selectedVersion}
            <div class="rounded-2xl bg-[var(--civ-panel-raised,#1a2636)] border border-[var(--civ-border,rgba(42,58,78,0.6))] p-5 shadow-lg" data-testid="download-section">
              <!-- header row -->
              <div class="flex items-center justify-between mb-3.5">
                <h3 class="text-base font-bold text-[var(--civ-ink,#ecf4fb)] leading-none">Download</h3>
                {#if modelFiles.length}
                  <span class="text-xs font-medium text-[var(--civ-muted,#a0b2c6)]">{modelFiles.length} variant{modelFiles.length > 1 ? "s" : ""} available</span>
                {/if}
              </div>

              <!-- variant rows -->
              {#if modelFiles.length > 0}
                <div class="space-y-2 mb-4">
                  {#each modelFiles as file (file.id)}
                    {@const fdl = selectedVersion ? fileDl(file.id, selectedVersion.id) : null}
                    {@const sc = scanState(file)}
                    <div class="rounded-xl p-3 flex items-center gap-3 transition-colors {file.primary ? 'bg-black/30 border border-white/10' : 'bg-black/15 border border-transparent hover:bg-black/25'}">
                      <div class="shrink-0 w-10 h-10 rounded-xl bg-[var(--civ-panel,#131c29)] border border-white/10 flex items-center justify-center text-[var(--civ-accent,#67e8c6)] shadow-inner">
                        {@render typeIcon(file.type || modelType)}
                      </div>
                      <div class="min-w-0 flex-1">
                        <div class="flex items-center gap-1.5 flex-wrap">
                          <span class="text-sm text-white font-bold">{file.format || "SafeTensor"}</span>
                          {#if file.fp}<span class="shrink-0 text-[10px] font-bold uppercase text-[var(--civ-ink,#ecf4fb)] bg-white/10 px-1.5 py-0.5 rounded">{file.fp}</span>{/if}
                          <span class="shrink-0 text-[10px] font-bold uppercase tracking-wider text-[var(--civ-accent,#67e8c6)] bg-[var(--civ-accent,#67e8c6)]/15 border border-[var(--civ-accent,#67e8c6)]/30 px-1.5 py-0.5 rounded">{typeLabel(file.type || modelType)}</span>
                          {#if file.primary}
                            <span class="shrink-0 text-[10px] font-bold uppercase tracking-wider text-[var(--civ-warm,#ffc982)] bg-[var(--civ-warm,#ffc982)]/15 border border-[var(--civ-warm,#ffc982)]/30 px-1.5 py-0.5 rounded">Primary</span>
                          {/if}
                        </div>
                        <p class="text-xs text-[var(--civ-muted,#a0b2c6)] truncate mt-0.5" title={file.name}>{file.name}</p>
                        <div class="flex items-center gap-2 mt-1 flex-wrap text-xs">
                          <!-- verified/scan shield -->
                          <span class="inline-flex items-center gap-1 text-xs font-semibold {sc.ok ? 'text-emerald-400' : sc.pending ? 'text-amber-400' : 'text-rose-400'}" title={file.scannedAt ? `Scanned ${sc.when}` : 'Not scanned yet'}>
                            {#if sc.ok}
                              <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2l7 3v6c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V5l7-3z"/><polyline points="9 12 11 14 15 10"/></svg>
                            {:else}
                              <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2l7 3v6c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V5l7-3z"/><path d="M12 8v4M12 16h.01"/></svg>
                            {/if}
                            {sc.label}
                          </span>
                          <span class="text-[10px] text-[var(--civ-muted,#a0b2c6)]">{sc.when}</span>
                          {#if file.sizeType}<span class="text-xs text-[var(--civ-muted,#a0b2c6)]">{file.sizeType}</span>{/if}
                          {#if fdl?.status === "queued" || fdl?.status === "pending"}<span class="text-xs text-sky-400 font-medium">queued…</span>
                          {:else if fdl?.status === "completed" || isInstalled(file.id)}<span class="text-xs text-emerald-400 font-semibold">✓ downloaded</span>
                          {:else if fStatus(file.id) === "incomplete" || fStatus(file.id) === "corrupt"}<span class="text-xs text-amber-400 font-semibold">⚠ incomplete — re-download</span>{/if}
                          {#if fdl && (fdl.status === "failed" || fdl.status === "gone")}<span class="text-xs text-rose-400 font-semibold" title={fdl.error}>failed</span>{/if}
                        </div>
                        {#if fdl?.status === "downloading"}
                          <div class="mt-2 h-1.5 rounded-full bg-black/40 border border-white/10 overflow-hidden">
                            <div class="h-full bg-gradient-to-r from-[var(--civ-accent,#67e8c6)] to-sky-400 transition-all duration-500" style="width:{fdl.progress}%"></div>
                          </div>
                          <div class="text-[10px] text-[var(--civ-muted,#a0b2c6)] mt-1 font-mono">
                            {fmtSize(fdl.bytesDownloaded || 0)} / {fmtSize(fdl.bytesTotal || 0)} · {fdl.progress}%{fmtSpeed(fdl.speed || 0) ? ` · ${fmtSpeed(fdl.speed || 0)}` : ""}{fmtEta(fdl.etaSec || 0) ? ` · ETA ${fmtEta(fdl.etaSec || 0)}` : ""}
                          </div>
                        {/if}
                      </div>
                      <span class="text-xs text-[var(--civ-ink,#ecf4fb)] font-semibold shrink-0">{fmtS(file.sizeKB)}</span>
                      <button
                        class="shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200 cursor-pointer disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--civ-accent,#67e8c6)]
                          {isInstalled(file.id) ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-500/40' : fileNeedsApiKey(file) ? 'bg-rose-950/60 text-rose-400 border border-rose-500/40 hover:bg-rose-600 hover:text-white' : 'bg-black/40 border border-white/15 hover:bg-[var(--civ-accent,#67e8c6)] text-white hover:text-[#0b1018]'}"
                        onclick={() => download(file)}
                        disabled={isActive(fdl) || (isInstalled(file.id) && fdl?.status !== 'failed' && fdl?.status !== 'gone') || fileNeedsApiKey(file)}
                        title={isInstalled(file.id) ? "Already downloaded (healthy)" : fileNeedsApiKey(file) ? "API key required — click to open civitai.com" : `Download ${file.name}`}
                        aria-label={isInstalled(file.id) ? "Already installed" : fileNeedsApiKey(file) ? "API key required" : `Download ${file.name}`}
                      >
                        {#if isActive(fdl)}
                          <svg class="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 12a9 9 0 11-6.2-8.6"/></svg>
                        {:else if fdl?.status === "completed" || isInstalled(file.id)}
                          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                        {:else}
                          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/></svg>
                        {/if}
                      </button>
                    </div>
                  {/each}
                </div>
              {/if}

              <!-- primary download button -->
              {#if isBuzzModel}
                <div class="flex items-center gap-2 mb-2.5 px-3.5 py-2 rounded-xl bg-amber-950/40 border border-amber-500/40 text-amber-300 text-xs font-semibold">
                  <svg class="w-4 h-4 shrink-0 text-amber-400" viewBox="0 0 24 24" fill="currentColor"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                  <span>Requires Buzz — unlock on civitai.com</span>
                </div>
              {/if}

              <button
                class="w-full py-3 rounded-xl text-sm font-bold text-[#0b1018] active:scale-[0.99] transition-all duration-200 flex items-center justify-center gap-2 disabled:opacity-80 border cursor-pointer shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--civ-accent,#67e8c6)]
                  {primaryDl?.status === 'completed' || isInstalled(primaryFile?.id) ? 'bg-emerald-500 text-white border-emerald-400 hover:bg-emerald-600' : buzzLocked ? 'bg-zinc-700 text-white border-zinc-600' : anyFileNeedsApiKey ? 'bg-rose-700 text-white border-rose-600 hover:bg-rose-800' : 'bg-[var(--civ-accent,#67e8c6)] border-[var(--civ-accent,#67e8c6)] hover:bg-[#86efac] shadow-[0_0_18px_rgba(103,232,198,0.4)]'}"
                onclick={downloadPrimary}
                disabled={isActive(primaryDl) || modelFiles.length === 0 || buzzLocked || (isInstalled(primaryFile?.id) && primaryDl?.status !== "failed" && primaryDl?.status !== "gone")}
                data-testid="download-btn"
              >
                {#if primaryDl?.status === "queued" || primaryDl?.status === "pending"}
                  <svg class="w-4 h-4 animate-spin text-[#0b1018]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 12a9 9 0 11-6.2-8.6"/></svg>
                  <span>Queued…</span>
                {:else if primaryDl?.status === "downloading"}
                  <svg class="w-4 h-4 animate-spin text-[#0b1018]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 12a9 9 0 11-6.2-8.6"/></svg>
                  <span>Downloading… {primaryDl.progress}%</span>
                {:else if primaryDl?.status === "completed" || isInstalled(primaryFile?.id)}
                  <svg class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                  <span class="text-white">Installed</span>
                {:else if buzzLocked}
                  <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="0"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 018 0v4" fill="none" stroke="currentColor" stroke-width="2"/></svg>
                  <span class="tracking-wide">Buy on civitai.com</span>
                {:else if anyFileNeedsApiKey}
                  <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="0"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 018 0v4" fill="none" stroke="currentColor" stroke-width="2"/></svg>
                  <span class="tracking-wide">API key required</span>
                {:else}
                  <svg class="w-4 h-4 text-[#0b1018]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/></svg>
                  <span class="tracking-wide text-[#0b1018]">Download{primaryFile && primaryFile.sizeKB ? ` (${fmtS(primaryFile.sizeKB)})` : ""}</span>
                {/if}
              </button>
              {#if primaryDl?.status === "downloading"}
                <div class="mt-2.5 h-1.5 rounded-full bg-black/40 border border-white/10 overflow-hidden">
                  <div class="h-full bg-gradient-to-r from-[var(--civ-accent,#67e8c6)] to-sky-400 transition-all duration-500" style="width:{primaryDl.progress}%"></div>
                </div>
                <div class="flex justify-between mt-1 text-[10px] text-[var(--civ-muted,#a0b2c6)] font-mono">
                  <span>{fmtSize(primaryDl.bytesDownloaded || 0)} / {fmtSize(primaryDl.bytesTotal || 0)}</span>
                  <span>{primaryDl.progress}%</span>
                </div>
              {/if}
              {#if primaryDl && (primaryDl.status === "failed" || primaryDl.status === "gone")}
                <p class="text-xs font-semibold text-rose-400 mt-2 text-center">{primaryDl.error || "Download failed"}</p>
              {/if}
              {#if activeCount > 0 && totalSpeed > 0}
                <div class="flex items-center justify-center gap-1.5 mt-2.5 text-xs text-[var(--civ-accent,#67e8c6)] font-semibold">
                  <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
                  <span>{activeCount} active · {fmtSpeed(totalSpeed)} total</span>
                </div>
              {/if}
              {#if modelType}
                <p class="text-xs text-[var(--civ-muted,#a0b2c6)] mt-2 text-center">→ models/{DIR_MAP[modelType] || "Stable-diffusion"}</p>
              {/if}
            </div>
          {/if}

          <!-- required components / dependencies -->
          {#if componentFiles.length || selectedVersion?.dependencies?.length}
            {@const deps = (selectedVersion?.dependencies || []).filter((d) => !componentFiles.some((f) => f.name === d.name || f.id === d.fileId))}
            {@const compCount = componentFiles.length + deps.length}
            {@const compTotalKB = componentFiles.reduce((s, f) => s + (f.sizeKB || 0), 0) + deps.reduce((s, d) => s + (d.sizeKB || 0), 0)}
            {@const allCompInstalled = componentFiles.every((f) => isInstalled(f.id)) && deps.every((d) => isInstalled(d.fileId))}
            <div class="rounded-2xl bg-[var(--civ-panel-raised,#1a2636)] border border-[var(--civ-border,rgba(42,58,78,0.6))] p-5 shadow-lg" data-testid="dependencies">
              <div class="flex items-center gap-2 mb-1">
                <svg class="w-4 h-4 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>
                <h3 class="text-base font-bold text-white">Required Components</h3>
                <span class="text-xs font-bold text-amber-300 bg-amber-500/20 border border-amber-500/40 px-2 py-0.5 rounded-full">{compCount}</span>
              </div>
              <p class="text-xs text-[var(--civ-muted,#a0b2c6)] mb-3.5">You need these files to run this model.</p>
              <div class="space-y-2 mb-3.5">
                {#each componentFiles as file (file.id)}
                  {@const cfl = selectedVersion ? fileDl(file.id, selectedVersion.id) : null}
                  {@const cInst = isInstalled(file.id)}
                  <div class="rounded-xl p-3 bg-black/25 border border-white/10 flex items-center gap-3">
                    <div class="shrink-0 w-9 h-9 rounded-xl bg-amber-950/50 border border-amber-500/30 flex items-center justify-center text-amber-400">
                      {@render typeIcon(file.type)}
                    </div>
                    <div class="min-w-0 flex-1">
                      <div class="flex items-center gap-1.5">
                        <span class="text-[10px] font-bold uppercase tracking-wider text-amber-300 bg-amber-500/20 border border-amber-500/40 px-1.5 py-0.5 rounded">{typeLabel(file.type)}</span>
                      </div>
                      <p class="text-xs text-white truncate font-semibold mt-0.5" title={file.name}>{file.name}</p>
                      <div class="flex items-center gap-2 mt-0.5 text-xs">
                        <span class="text-[10px] text-[var(--civ-muted,#a0b2c6)]">→ models/{fileTargetDir(file)}</span>
                        {#if cfl?.status === "queued" || cfl?.status === "pending"}<span class="text-[10px] text-amber-400 font-medium">queued…</span>
                        {:else if cfl?.status === "completed" || cInst}<span class="text-[10px] text-emerald-400 font-semibold">✓ downloaded</span>
                        {:else if fStatus(file.id) === "incomplete" || fStatus(file.id) === "corrupt"}<span class="text-[10px] text-amber-400 font-semibold">⚠ incomplete — re-download</span>{/if}
                        {#if cfl && (cfl.status === "failed" || cfl.status === "gone")}<span class="text-[10px] text-rose-400 font-semibold" title={cfl.error}>failed</span>{/if}
                      </div>
                      {#if cfl?.status === "downloading"}
                        <div class="mt-1.5 h-1 rounded-full bg-black/40 overflow-hidden">
                          <div class="h-full bg-amber-400 transition-all duration-500" style="width:{cfl.progress}%"></div>
                        </div>
                        <div class="text-[10px] text-[var(--civ-muted,#a0b2c6)] mt-0.5 font-mono">
                          {fmtSize(cfl.bytesDownloaded || 0)} / {fmtSize(cfl.bytesTotal || 0)} · {cfl.progress}%{fmtSpeed(cfl.speed || 0) ? ` · ${fmtSpeed(cfl.speed || 0)}` : ""}{fmtEta(cfl.etaSec || 0) ? ` · ETA ${fmtEta(cfl.etaSec || 0)}` : ""}
                        </div>
                      {/if}
                    </div>
                    <span class="text-xs text-[var(--civ-muted,#a0b2c6)] font-semibold shrink-0">{fmtS(file.sizeKB)}</span>
                    <button
                      class="shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200 cursor-pointer disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--civ-accent,#67e8c6)]
                        {(cfl?.status === 'completed' || cInst) ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-500/40' : 'bg-black/40 border border-white/15 hover:bg-amber-400 text-white hover:text-[#0b1018]'}"
                      onclick={() => download(file)}
                      disabled={isActive(cfl) || (cInst && cfl?.status !== 'failed' && cfl?.status !== 'gone')}
                      title={cInst ? "Already downloaded (healthy)" : `Download ${file.name}`}
                      aria-label={`Download ${file.name}`}
                    >
                      {#if isActive(cfl)}
                        <svg class="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 12a9 9 0 11-6.2-8.6"/></svg>
                      {:else if cfl?.status === "completed" || cInst}
                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                      {:else}
                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/></svg>
                      {/if}
                    </button>
                  </div>
                {/each}
                {#each deps as dep (dep.versionId + '-' + (dep.fileId ?? '0'))}
                  {@const ddl = fileDl(dep.fileId ?? -1, dep.versionId)}
                  {@const dInst = isInstalled(dep.fileId)}
                  <div class="rounded-xl p-3 bg-black/25 border border-white/10 flex items-center gap-3">
                    <div class="shrink-0 w-9 h-9 rounded-xl bg-amber-950/50 border border-amber-500/30 flex items-center justify-center text-amber-400">
                      {@render typeIcon(dep.type)}
                    </div>
                    <div class="min-w-0 flex-1">
                      <div class="flex items-center gap-1.5">
                        <span class="text-[10px] font-bold uppercase tracking-wider text-amber-300 bg-amber-500/20 border border-amber-500/40 px-1.5 py-0.5 rounded">{typeLabel(dep.type)}</span>
                        {#if dep.required}<span class="text-[10px] text-rose-400 font-bold">required</span>{/if}
                      </div>
                      <p class="text-xs text-white truncate font-semibold mt-0.5" title={dep.name}>{dep.name}</p>
                      <div class="flex items-center gap-2 mt-0.5 text-xs">
                        <span class="text-[10px] text-[var(--civ-muted,#a0b2c6)]">→ models/{depDir(dep)}</span>
                        {#if ddl?.status === "queued" || ddl?.status === "pending"}<span class="text-[10px] text-amber-400 font-medium">queued…</span>
                        {:else if ddl?.status === "completed" || dInst}<span class="text-[10px] text-emerald-400 font-semibold">✓ downloaded</span>
                        {:else if fStatus(dep.fileId) === "incomplete" || fStatus(dep.fileId) === "corrupt"}<span class="text-[10px] text-amber-400 font-semibold">⚠ incomplete — re-download</span>{/if}
                        {#if ddl && (ddl.status === "failed" || ddl.status === "gone")}<span class="text-[10px] text-rose-400 font-semibold" title={ddl.error}>failed</span>{/if}
                      </div>
                      {#if ddl?.status === "downloading"}
                        <div class="mt-1.5 h-1 rounded-full bg-black/40 overflow-hidden">
                          <div class="h-full bg-amber-400 transition-all duration-500" style="width:{ddl.progress}%"></div>
                        </div>
                        <div class="text-[10px] text-[var(--civ-muted,#a0b2c6)] mt-0.5 font-mono">
                          {fmtSize(ddl.bytesDownloaded || 0)} / {fmtSize(ddl.bytesTotal || 0)} · {ddl.progress}%{fmtSpeed(ddl.speed || 0) ? ` · ${fmtSpeed(ddl.speed || 0)}` : ""}{fmtEta(ddl.etaSec || 0) ? ` · ETA ${fmtEta(ddl.etaSec || 0)}` : ""}
                        </div>
                      {/if}
                    </div>
                    <span class="text-xs text-[var(--civ-muted,#a0b2c6)] font-semibold shrink-0">{fmtS(dep.sizeKB)}</span>
                    <button
                      class="shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200 cursor-pointer disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--civ-accent,#67e8c6)]
                        {(ddl?.status === 'completed' || dInst) ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-500/40' : 'bg-black/40 border border-white/15 hover:bg-amber-400 text-white hover:text-[#0b1018]'}"
                      onclick={() => downloadDep(dep)}
                      disabled={isActive(ddl) || (dInst && ddl?.status !== 'failed' && ddl?.status !== 'gone')}
                      title={dInst ? "Already downloaded (healthy)" : `Download ${dep.name}`}
                      aria-label={`Download ${dep.name}`}
                    >
                      {#if isActive(ddl)}
                        <svg class="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 12a9 9 0 11-6.2-8.6"/></svg>
                      {:else if ddl?.status === "completed" || dInst}
                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                      {:else}
                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/></svg>
                      {/if}
                    </button>
                  </div>
                {/each}
              </div>
              {#if compCount > 1}
                {#if allCompInstalled}
                  <div class="w-full py-2.5 rounded-xl text-xs font-bold text-emerald-400 bg-emerald-950/40 border border-emerald-500/40 flex items-center justify-center gap-2">
                    <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2l7 3v6c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V5l7-3z"/><polyline points="9 12 11 14 15 10"/></svg>
                    <span>All components installed</span>
                  </div>
                {:else}
                  <button
                    class="w-full py-2.5 rounded-xl text-xs font-bold text-[#0b1018] bg-amber-400 hover:bg-amber-300 active:scale-[0.99] transition-all duration-200 flex items-center justify-center gap-2 cursor-pointer shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300"
                    onclick={downloadAllDeps}
                    aria-label="Download all components"
                  >
                    <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/></svg>
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
            <div class="rounded-2xl bg-[var(--civ-panel-raised,#1a2636)] border border-[var(--civ-border,rgba(42,58,78,0.6))] p-4 shadow-sm">
              <h3 class="text-xs font-bold text-[var(--civ-muted,#a0b2c6)] uppercase tracking-wider mb-2.5">License</h3>
              <div class="flex flex-wrap gap-1.5">
                {#if cUse === true}<span class="text-[10px] font-bold uppercase tracking-wider text-emerald-400 bg-emerald-950/40 border border-emerald-500/40 px-2.5 py-1 rounded-lg">Commercial</span>{:else if cUse === false}<span class="text-[10px] font-bold uppercase tracking-wider text-rose-400 bg-rose-950/40 border border-rose-500/40 px-2.5 py-1 rounded-lg">No Commercial Use</span>{:else if typeof cUse === 'string' && cUse}<span class="text-[10px] font-bold uppercase tracking-wider text-emerald-400 bg-emerald-950/40 border border-emerald-500/40 px-2.5 py-1 rounded-lg">Commercial ({cUse})</span>{/if}
                {#if deriv === true}<span class="text-[10px] font-bold uppercase tracking-wider text-emerald-400 bg-emerald-950/40 border border-emerald-500/40 px-2.5 py-1 rounded-lg">Derivatives</span>{:else if deriv === false}<span class="text-[10px] font-bold uppercase tracking-wider text-rose-400 bg-rose-950/40 border border-rose-500/40 px-2.5 py-1 rounded-lg">No Derivatives</span>{/if}
                {#if noCredit === false}<span class="text-[10px] font-bold uppercase tracking-wider text-amber-300 bg-amber-950/40 border border-amber-500/40 px-2.5 py-1 rounded-lg">Credit Required</span>{/if}
                {#if selectedVersion?.allowDifferentLicense === true}<span class="text-[10px] font-bold uppercase tracking-wider text-orange-300 bg-orange-950/40 border border-orange-500/40 px-2.5 py-1 rounded-lg">Mixed License Terms</span>{/if}
              </div>
            </div>
          {/if}

          <!-- details table -->
          <div>
            <h3 class="text-xs font-bold text-[var(--civ-muted,#a0b2c6)] uppercase tracking-wider mb-2.5">Details</h3>
            <div class="rounded-2xl border border-[var(--civ-border,rgba(42,58,78,0.6))] overflow-hidden text-xs bg-[var(--civ-panel-raised,#1a2636)] shadow-sm">
              {#if modelType}
                <div class="flex justify-between px-4 py-2.5 bg-black/20 border-b border-white/5">
                  <span class="text-[var(--civ-muted,#a0b2c6)] font-medium">Type</span><span class="text-[var(--civ-ink,#ecf4fb)] font-bold">{modelType}</span>
                </div>
              {/if}
              {#if selectedVersion?.baseModel}
                <div class="flex justify-between px-4 py-2.5 border-b border-white/5">
                  <span class="text-[var(--civ-muted,#a0b2c6)] font-medium">Base Model</span><span class="text-[var(--civ-accent,#67e8c6)] font-bold">{selectedVersion.baseModel}</span>
                </div>
              {/if}
              {#if published}
                <div class="flex justify-between px-4 py-2.5 bg-black/20 border-b border-white/5">
                  <span class="text-[var(--civ-muted,#a0b2c6)] font-medium">Published</span><span class="text-[var(--civ-ink,#ecf4fb)] font-medium">{published}</span>
                </div>
              {/if}
              <div class="flex justify-between px-4 py-2.5 border-b border-white/5">
                <span class="text-[var(--civ-muted,#a0b2c6)] font-medium">Downloads</span><span class="text-[var(--civ-ink,#ecf4fb)] font-bold">{fmtCount((model.stats || {}).downloadCount || 0)}</span>
              </div>
              {#if review}
                <div class="flex justify-between px-4 py-2.5 border-b border-white/5 gap-2">
                  <span class="text-[var(--civ-muted,#a0b2c6)] font-medium">Reviews</span>
                  <span class="{review.positive ? 'text-emerald-400' : 'text-amber-400'} font-bold text-right">{review.label} <span class="text-[var(--civ-muted,#a0b2c6)] font-normal">({fmtCount(review.total)})</span></span>
                </div>
              {/if}
              {#if hashStr}
                <div class="flex justify-between items-center px-4 py-2.5 bg-black/20 border-b border-white/5 gap-2">
                  <span class="text-[var(--civ-muted,#a0b2c6)] font-medium">Hash</span>
                  <button
                    class="inline-flex items-center gap-1.5 min-w-0 text-[var(--civ-ink,#ecf4fb)] font-mono hover:text-[var(--civ-accent,#67e8c6)] transition-colors cursor-pointer"
                    onclick={() => copyWord(hashStr)}
                    title="Click to copy hash"
                  >
                    <span class="truncate">{copied === hashStr ? "copied!" : hashStr}</span>
                    <svg class="w-4 h-4 shrink-0 {copied === hashStr ? 'text-emerald-400' : 'text-[var(--civ-muted,#a0b2c6)]'}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
                  </button>
                </div>
              {/if}
              {#if selectedVersion?.clipSkip != null}
                <div class="flex justify-between px-4 py-2.5 border-b border-white/5">
                  <span class="text-[var(--civ-muted,#a0b2c6)] font-medium">Clip Skip</span><span class="text-[var(--civ-ink,#ecf4fb)] font-bold">{selectedVersion.clipSkip}</span>
                </div>
              {/if}
              {#if selectedVersion?.epochs != null}
                <div class="flex justify-between px-4 py-2.5 bg-black/20 border-b border-white/5">
                  <span class="text-[var(--civ-muted,#a0b2c6)] font-medium">Epochs</span><span class="text-[var(--civ-ink,#ecf4fb)] font-bold">{selectedVersion.epochs}</span>
                </div>
              {/if}
              {#if selectedVersion?.steps != null}
                <div class="flex justify-between px-4 py-2.5 border-b border-white/5">
                  <span class="text-[var(--civ-muted,#a0b2c6)] font-medium">Steps</span><span class="text-[var(--civ-ink,#ecf4fb)] font-bold">{fmtCount(selectedVersion.steps!)}</span>
                </div>
              {/if}
              {#if selectedVersion?.tensorType}
                <div class="flex justify-between px-4 py-2.5 bg-black/20 border-b border-white/5">
                  <span class="text-[var(--civ-muted,#a0b2c6)] font-medium">Tensor Type</span><span class="text-[var(--civ-ink,#ecf4fb)] font-bold">{selectedVersion.tensorType}</span>
                </div>
              {/if}
              {#if selectedVersion?.modelSize}
                <div class="flex justify-between px-4 py-2.5 border-b border-white/5">
                  <span class="text-[var(--civ-muted,#a0b2c6)] font-medium">Model Size</span><span class="text-[var(--civ-ink,#ecf4fb)] font-bold">{selectedVersion.modelSize}</span>
                </div>
              {/if}
              {#if (selectedVersion as any)?.tensorCount != null}
                <div class="flex justify-between px-4 py-2.5 bg-black/20">
                  <span class="text-[var(--civ-muted,#a0b2c6)] font-medium">Tensors</span><span class="text-[var(--civ-ink,#ecf4fb)] font-bold">{fmtCount((selectedVersion as any).tensorCount)}</span>
                </div>
              {/if}
            </div>
          </div>

          <!-- trigger words -->
          {#if selectedVersion?.trainedWords?.length}
            <div>
              <h3 class="text-xs font-bold text-[var(--civ-muted,#a0b2c6)] uppercase tracking-wider mb-2.5">Trigger Words</h3>
              <div class="flex flex-wrap gap-2">
                {#each selectedVersion.trainedWords as w (w)}
                  <button
                    class="px-3 py-1.5 bg-[var(--civ-panel-raised,#1a2636)] rounded-xl text-xs font-mono border transition-all duration-200 cursor-pointer shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--civ-accent,#67e8c6)]
                      {copied === w ? 'text-emerald-400 border-emerald-400' : 'text-[var(--civ-accent,#67e8c6)] border-[var(--civ-border,rgba(42,58,78,0.6))] hover:bg-black/30 hover:border-white/30'}"
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
            <div class="rounded-2xl bg-[var(--civ-panel-raised,#1a2636)] border border-[var(--civ-border,rgba(42,58,78,0.6))] overflow-hidden shadow-sm">
              <button
                class="w-full flex items-center justify-between px-4 py-3.5 text-left hover:bg-black/20 transition-colors cursor-pointer border-b border-white/5"
                onclick={(e) => {
                  const btn = e.currentTarget;
                  const content = btn.nextElementSibling as HTMLElement;
                  const open = !btn.classList.contains("collapsed");
                  if (open) {
                    content.style.maxHeight = "0px";
                    btn.classList.remove("border-b");
                    btn.classList.add("collapsed");
                  } else {
                    content.style.maxHeight = content.scrollHeight + "px";
                    btn.classList.add("border-b");
                    btn.classList.remove("collapsed");
                  }
                }}
              >
                <span class="text-xs font-bold text-[var(--civ-ink,#ecf4fb)]">About this version{selectedVersion?.name ? ` — ${selectedVersion.name}` : ""}</span>
                <svg class="w-4 h-4 text-[var(--civ-muted,#a0b2c6)] transition-transform duration-200 expand-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="m6 9 6 6 6-6"/></svg>
              </button>
              <div class="overflow-hidden transition-all duration-200" style="max-height:2000px">
                <div class="px-4 py-3.5 text-xs leading-relaxed text-[var(--civ-muted,#a0b2c6)]
                  [&_a]:text-[var(--civ-accent,#67e8c6)] [&_a]:underline
                  [&_em]:text-[var(--civ-ink,#ecf4fb)]
                  [&_strong]:text-white [&_strong]:font-semibold
                  [&_code]:text-[var(--civ-accent,#67e8c6)] [&_code]:bg-black/40 [&_code]:px-1 [&_code]:rounded
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
              <h3 class="text-xs font-bold text-[var(--civ-muted,#a0b2c6)] uppercase tracking-wider mb-2.5">Tags</h3>
              <div class="flex flex-wrap gap-1.5" data-testid="tags">
                {#each modelTags as t (t)}
                  <button
                    class="px-3 py-1 bg-[var(--civ-panel-raised,#1a2636)] rounded-full text-xs text-[var(--civ-muted,#a0b2c6)] border border-[var(--civ-border,rgba(42,58,78,0.6))] uppercase tracking-wider hover:bg-[var(--civ-accent,#67e8c6)] hover:text-[#0b1018] hover:border-[var(--civ-accent,#67e8c6)] cursor-pointer transition-all duration-200 shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--civ-accent,#67e8c6)]"
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
            <div class="rounded-2xl bg-[var(--civ-panel-raised,#1a2636)] border border-[var(--civ-border,rgba(42,58,78,0.6))] overflow-hidden shadow-sm">
              <h3 class="text-xs font-bold text-[var(--civ-muted,#a0b2c6)] uppercase tracking-wider px-4 pt-3.5 pb-2.5">Discussion</h3>
              {#each comments.slice(0, 4) as c (c.id)}
                <div class="px-4 py-3 border-t border-white/5">
                  <div class="flex items-center gap-2 mb-1.5">
                    {#if c.user?.image}
                      <img class="w-5 h-5 rounded-full object-cover" src={c.user.image} alt="" />
                    {:else}
                      <div class="w-5 h-5 rounded-full bg-black/40 flex items-center justify-center text-[10px] text-white/80 font-bold">{c.user?.username?.charAt(0)?.toUpperCase() || "?"}</div>
                    {/if}
                    <span class="text-xs font-semibold text-[var(--civ-ink,#ecf4fb)]">{c.user?.username || "Unknown"}</span>
                    <span class="text-[10px] text-[var(--civ-muted,#a0b2c6)] ml-auto">{c.createdAt ? new Date(c.createdAt).toLocaleDateString() : ""}</span>
                  </div>
                  <p class="text-xs text-[var(--civ-muted,#a0b2c6)] leading-relaxed line-clamp-3">{@html sanitizeHtml(c.content)}</p>
                </div>
              {/each}
              {#if commentsCursor}
                <button
                  class="block w-full text-center text-xs font-semibold text-[var(--civ-accent,#67e8c6)] hover:underline py-3 border-t border-white/5 transition-colors cursor-pointer"
                  onclick={loadMoreComments}
                  disabled={commentsLoading}
                >{commentsLoading ? "Loading…" : "Load more comments"}</button>
              {/if}
              <a
                class="block text-center text-xs font-medium text-[var(--civ-muted,#a0b2c6)] hover:text-white py-2.5 border-t border-white/5 no-underline transition-colors"
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
    background:
      radial-gradient(circle at 18% 10%, rgba(103, 232, 198, 0.12), transparent 34%),
      radial-gradient(circle at 82% 92%, rgba(183, 164, 255, 0.1), transparent 32%),
      rgba(11, 16, 24, 0.92);
    backdrop-filter: blur(20px) saturate(0.9);
  }

  .popup-canvas {
    border: 1px solid var(--civ-border, rgba(42, 58, 78, 0.6));
    border-radius: 24px;
    background:
      linear-gradient(145deg, rgba(19, 28, 41, 0.98), rgba(11, 16, 24, 0.99) 60%),
      var(--civ-bg, #0b1018);
    box-shadow: 0 36px 100px rgba(0, 0, 0, 0.75), 0 0 0 1px rgba(255, 255, 255, 0.05) inset;
  }

  .popup-close:hover {
    transform: rotate(90deg) scale(1.05);
  }

  .popup-workspace {
    background-image: linear-gradient(rgba(255, 255, 255, 0.015) 1px, transparent 1px);
    background-size: 100% 56px;
  }

  .popup-media-column {
    scrollbar-color: var(--civ-border, rgba(42, 58, 78, 0.6)) transparent;
  }

  .popup-viewer {
    background:
      radial-gradient(circle at 50% 0%, rgba(103, 232, 198, 0.08), transparent 50%),
      linear-gradient(180deg, rgba(255, 255, 255, 0.015), transparent);
  }

  .popup-description {
    position: relative;
    border-top: 1px solid var(--civ-border, rgba(42, 58, 78, 0.6));
    background: rgba(11, 16, 24, 0.6);
  }

  .popup-description::before {
    position: absolute;
    top: -1px;
    left: 32px;
    width: 90px;
    height: 1px;
    content: "";
    background: linear-gradient(90deg, var(--civ-accent, #67e8c6), transparent);
  }

  .popup-inspector {
    border-left: 1px solid var(--civ-border, rgba(42, 58, 78, 0.6));
    background: rgba(15, 22, 33, 0.9);
    box-shadow: -22px 0 60px rgba(0, 0, 0, 0.25);
    scrollbar-color: var(--civ-border, rgba(42, 58, 78, 0.6)) transparent;
  }
  .popup-inspector [data-testid="download-section"],
  .popup-inspector [data-testid="dependencies"],
  .popup-inspector :global(.creator-card) {
    border-color: var(--civ-border, rgba(42, 58, 78, 0.6));
    border-radius: 16px;
    background: linear-gradient(145deg, var(--civ-panel-raised, #1a2636), rgba(19, 28, 41, 0.8));
    box-shadow: 0 12px 34px rgba(0, 0, 0, 0.25), 0 1px 0 rgba(255, 255, 255, 0.04) inset;
  }

  @media (max-width: 1024px) {
    .popup-backdrop { padding: 0; }
    .popup-canvas { width: 100vw; height: 100dvh; border: 0; border-radius: 0; }
    .popup-workspace { flex-direction: column; overflow-y: auto; }
    .popup-media-column { overflow: visible; }
    .popup-inspector { width: 100%; overflow: visible; border-top: 1px solid var(--civ-border, rgba(42, 58, 78, 0.6)); border-left: 0; }
  }

  @media (prefers-reduced-motion: reduce) {
    .popup-canvas, .popup-close, .expand-arrow { transition: none !important; transform: none !important; }
  }
</style>
