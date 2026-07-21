<script lang="ts">
  import { appState } from "./stores.svelte.ts";
  import type { CivitaiModel, ModelVersion, ModelFile, ModelDependency } from "./stores.svelte.ts";

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

  const MODELS_ROOT = "/home/gonzo/webui/sd-webui-forge-classic/models";
  const DIR_MAP: Record<string, string> = {
    Checkpoint: "Stable-diffusion",
    LORA: "Lora",
    LoCon: "Lora",
    DoRA: "Lora",
    LoRA: "Lora",
    TextualInversion: "embeddings",
    Hypernetwork: "hypernetworks",
    VAE: "VAE",
    Controlnet: "ControlNet",
    Upscaler: "ESRGAN",
    MotionModule: "AnimateDiff",
    Poses: "Poses",
    Wildcards: "wildcards",
  };

  // Map a component/file type (or filename) to the correct WebUI subdirectory.
  // Fixes VAE / text-encoder files landing in the checkpoint folder.
  function subdirForType(t: string): string {
    const s = (t || "").toLowerCase();
    if (s.includes("vae")) return "VAE";
    if (s.includes("encoder") || s.includes("text encoder") || s === "te") return "text_encoder";
    if (s.includes("lora") || s.includes("locon") || s.includes("dora")) return "Lora";
    if (s.includes("embed") || s.includes("textualinversion")) return "embeddings";
    if (s.includes("controlnet")) return "ControlNet";
    if (s.includes("upscal") || s.includes("esrgan")) return "ESRGAN";
    if (s.includes("checkpoint")) return "Stable-diffusion";
    return "";
  }
  function fileTargetDir(file: ModelFile): string {
    const byType = subdirForType(file.type || "");
    if (byType && byType !== "Stable-diffusion") return byType;
    const n = (file.name || "").toLowerCase();
    if (/(^|[_\-.])vae([_\-.]|$)/.test(n)) return "VAE";
    if (/text.?encoder|(^|[_\-.])te([_\-.]|$)|(^|[_\-.])txt([_\-.]|$)|t5xxl|clip[_\-]?[lg]/.test(n)) return "text_encoder";
    return DIR_MAP[modelType] || byType || "Stable-diffusion";
  }
  function depDir(dep: ModelDependency): string {
    const byType = subdirForType(dep.type || "");
    if (byType) return byType;
    const n = (dep.name || dep.modelName || "").toLowerCase();
    if (/vae/.test(n)) return "VAE";
    if (/encoder|(^|[_\-.])te([_\-.]|$)|txt|t5|clip/.test(n)) return "text_encoder";
    return "Stable-diffusion";
  }

  let showLb = $state(false);
  let lbIdx = $state(0);
  let activeImg = $state(0);
  // Per-download state lives in the global store so progress persists across popup
  // open/close. See appState.downloads / queueDownload / pollDownloads.
  interface DlState { fileId: number | null; versionId: number; status: string; progress: number; bytesDownloaded?: number; bytesTotal?: number; speed?: number; etaSec?: number; error?: string }
  let copied = $state("");
  let carouselEl = $state<HTMLDivElement | null>(null);

  let galleryImages = $derived.by(() => {
    const src = selectedVersion?.images?.length
      ? selectedVersion.images
      : Array.isArray(model.images)
        ? model.images
        : [];
    const seen = new Set<string>();
    const out: any[] = [];
    for (const img of src) {
      if (img?.url && !seen.has(img.url)) {
        seen.add(img.url);
        out.push(img);
      }
    }
    return out;
  });

  // Enlarged row slides so the selected image is always shown (clamped to the end).
  let pageStart = $derived(Math.max(0, Math.min(activeImg, galleryImages.length - 4)));
  let heroImages = $derived(galleryImages.slice(pageStart, pageStart + 4));

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
    if ((model as any).hasBuzz === true) return true;
    if ((model as any).availability === 'EarlyAccess') return true;
    if (selectedVersion && (selectedVersion as any).availability === 'EarlyAccess') return true;
    if (selectedVersion && (selectedVersion as any).buzzCost > 0) return true;
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

  function fmtN(n: number | undefined) {
    if (n == null) return "0";
    if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
    return String(n || 0);
  }
  function fmtS(kb: number) {
    if (!kb) return "";
    if (kb >= 1e6) return (kb / 1e6).toFixed(2) + " GB";
    if (kb >= 1e3) return (kb / 1e3).toFixed(1) + " MB";
    return kb.toFixed(0) + " KB";
  }
  function imgSrc(img: any, w = 600) {
    const u = img?.url || "";
    if (!u) return "";
    if (img?.type === "video") return u;
    let r = u.replace("/original=true/", "/");
    if (!r.includes("/width=")) {
      const b = r.includes("?") ? r.split("?")[0] : r;
      r = b + `/width=${w},format=webp`;
    }
    return r;
  }

  function pagePrev() {
    if (activeImg > 0) activeImg -= 1;
  }
  function pageNext() {
    if (activeImg < galleryImages.length - 1) activeImg += 1;
  }
  function openLb(globalIdx: number) {
    lbIdx = globalIdx;
    showLb = true;
  }
  function prevLb() {
    if (lbIdx > 0) lbIdx--;
  }
  function nextLb() {
    if (lbIdx < galleryImages.length - 1) lbIdx++;
  }

  // ---- Batched image loader ----------------------------------------------
  // Civitai's CDN rate-blocks / stalls when hit with many parallel requests
  // (4 hero + 20 carousel at once). This loader keeps only MAX_INFLIGHT requests
  // in flight, loading hero images first (low priority number = sooner), and only
  // starts the next image once an earlier one fully loads / errors / times out.
  const MAX_INFLIGHT = 3;
  interface ImgJob { node: HTMLImageElement; src: string; priority: number; started: boolean }
  let imgJobs: ImgJob[] = [];
  let imgInflight = 0;
  const imgCleanups = new WeakMap<ImgJob, () => void>();

  $effect(() => {
    return () => {
      for (const job of imgJobs) {
        imgCleanups.get(job)?.();
      }
      imgJobs = [];
      imgInflight = 0;
    };
  });

  function imgPump() {
    while (imgInflight < MAX_INFLIGHT) {
      let next: ImgJob | null = null;
      for (const j of imgJobs) {
        if (!j.started && (next === null || j.priority < next.priority)) next = j;
      }
      if (!next) break;
      imgStart(next);
    }
  }
  function imgSchedule() { queueMicrotask(imgPump); }

  function imgStart(job: ImgJob) {
    job.started = true;
    imgInflight++;
    const node = job.node;
    let tries = 0;
    let finished = false;
    let timer: ReturnType<typeof setTimeout>;
    const loaded = () => node.complete && node.naturalWidth > 0;
    const finish = () => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      node.removeEventListener("load", onload);
      node.removeEventListener("error", onerror);
      imgInflight--;
      imgJobs = imgJobs.filter((j) => j !== job);
      imgCleanups.delete(job);
      imgSchedule();
    };
    const attempt = () => {
      const base = job.src;
      node.src = tries === 0 ? base : base.includes("?") ? `${base}&_r=${tries}` : `${base}?_r=${tries}`;
      clearTimeout(timer);
      timer = setTimeout(() => { if (!loaded()) retry(); }, 5000);
    };
    const retry = () => {
      if (tries >= 6) { finish(); return; }
      tries++;
      clearTimeout(timer);
      timer = setTimeout(attempt, 400 + 400 * tries); // backoff lets transient resets recover
    };
    const onload = () => { if (loaded()) finish(); };
    const onerror = () => retry();
    node.addEventListener("load", onload);
    node.addEventListener("error", onerror);
    imgCleanups.set(job, () => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      node.removeEventListener("load", onload);
      node.removeEventListener("error", onerror);
      imgInflight--;
    });
    attempt();
  }

  function batchImg(node: HTMLImageElement, params: { src: string; priority?: number }) {
    let job: ImgJob = { node, src: params.src, priority: params.priority ?? 100, started: false };
    imgJobs = [...imgJobs, job];
    imgSchedule();
    return {
      update(p: { src: string; priority?: number }) {
        if (p.src && p.src !== job.src) {
          imgCleanups.get(job)?.();
          imgJobs = imgJobs.filter((j) => j !== job);
          node.removeAttribute("src");
          job = { node, src: p.src, priority: p.priority ?? 100, started: false };
          imgJobs = [...imgJobs, job];
          imgSchedule();
        } else if (p.priority != null) {
          job.priority = p.priority;
        }
      },
      destroy() {
        imgCleanups.get(job)?.();
        imgJobs = imgJobs.filter((j) => j !== job);
        imgSchedule();
      },
    };
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
    if (isActive(fileDl(file.id, selectedVersion.id))) return; // already downloading this file+version
    if (isInstalled(file.id)) return; // already downloaded & healthy — don't re-download
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
        sizeKB: file.sizeKB,
      });
    } catch (e) {
      const id = `err-${file.id}-${Date.now()}`;
      appState.downloads = { ...appState.downloads, [id]: { fileId: file.id, versionId: selectedVersion.id, modelId: model.id, fileName: file.name, status: "failed", progress: 0, error: e instanceof Error ? e.message : "Download failed" } };
    }
  }

  async function downloadDep(dep: ModelDependency) {
    if (isActive(fileDl(dep.fileId ?? -1, dep.versionId))) return;
    if (isInstalled(dep.fileId)) return; // already downloaded & healthy
    const dir = `${MODELS_ROOT}/${depDir(dep)}`;
    try {
      await appState.queueDownload({
        modelId: dep.modelId ?? 0,
        versionId: dep.versionId,
        fileId: dep.fileId ?? undefined,
        downloadUrl: dep.downloadUrl,
        downloadDir: dir,
        fileName: dep.name,
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
    appState.setFilter("modelType", modelType);
    // Clear other filters to maximize results — only the type + the tag search matter.
    (appState.filters as any).baseModel = [];
    (appState.filters as any).nsfw = (model as any).nsfw || appState.filters.nsfw;
    (appState.filters as any).sort = "Most Downloaded";
    (appState.filters as any).period = "AllTime";
    appState.triggerSearch();
    // Don't save — this is transient. The sidebar UX only reflects the current state,
    // but the persisted settings (from saveSettings) are untouched.
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
  function fmtAgo(iso: string | null | undefined): string {
    if (!iso) return "";
    const t = Date.parse(iso);
    if (isNaN(t)) return "";
    const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    if (s < 2592000) return `${Math.floor(s / 86400)}d ago`;
    if (s < 31536000) return `${Math.floor(s / 2592000)}mo ago`;
    return `${Math.floor(s / 31536000)}y ago`;
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
    const pf = files.find((f) => f.primary) || files[0];
    if (pf) download(pf);
  }

  // Make the thumbnail carousel scroll horizontally with the mouse wheel.
  function hscroll(node: HTMLElement) {
    const onWheel = (e: WheelEvent) => {
      if (e.deltaY !== 0 && node.scrollWidth > node.clientWidth) {
        e.preventDefault();
        node.scrollLeft += e.deltaY;
      }
    };
    node.addEventListener("wheel", onWheel, { passive: false });
    return { destroy() { node.removeEventListener("wheel", onWheel); } };
  }

  // Keep the active thumbnail visible as you navigate the enlarged view.
  // Scroll ONLY the carousel element (not scrollIntoView, which can scroll ancestors
  // and shove the whole layout when selecting thumbnails near the end).
  $effect(() => {
    const idx = activeImg;
    const el = carouselEl;
    if (!el) return;
    const btn = el.querySelectorAll("button")[idx] as HTMLElement | undefined;
    if (!btn) return;
    const target = btn.offsetLeft - (el.clientWidth - btn.clientWidth) / 2;
    const max = el.scrollWidth - el.clientWidth;
    el.scrollTo({ left: Math.max(0, Math.min(target, max)), behavior: "smooth" });
  });

  // Lazy-load videos (only fetch/play when visible) so a gallery of animated previews
  // doesn't download every full-size video at once.
  function lazyVideo(node: HTMLVideoElement, src: string) {
    let loaded = false;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            if (!loaded && src) { node.src = src; loaded = true; }
            node.play?.().catch(() => {});
          } else {
            node.pause?.();
          }
        }
      },
      { rootMargin: "150px" }
    );
    io.observe(node);
    return { destroy() { io.disconnect(); } };
  }

  // Aggregate state for the primary Download button (reflects the primary file only).
  let primaryFile = $derived(modelFiles.find((f) => f.primary) || modelFiles[0] || null);
  let primaryDl = $derived(
    primaryFile && selectedVersion ? fileDl(primaryFile.id, selectedVersion.id) : null,
  );

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
    if (showLb) {
      if (e.key === "Escape") showLb = false;
      else if (e.key === "ArrowLeft") prevLb();
      else if (e.key === "ArrowRight") nextLb();
      return;
    }
    if (e.key === "Escape") onClose();
  }}
/>

<div
  class="fixed inset-0 z-50 bg-black/75 flex items-center justify-center"
  onclick={onClose}
  onkeydown={(e) => { if (e.key === 'Escape') onClose(); }}
  role="presentation"
  data-testid="popup-backdrop"
>
  <div
    class="relative w-[92vw] h-[90vh] max-w-[1600px] rounded-2xl overflow-hidden bg-[#1a1b1e] flex flex-col shadow-2xl ring-1 ring-[#2c2e33]"
    role="dialog"
    aria-modal="true"
    tabindex="-1"
    data-testid="popup"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.stopPropagation()}
  >
    <!-- slim top bar -->
    <div class="shrink-0 flex items-center justify-between px-6 h-12 border-b border-[#2c2e33]">
      <span class="text-[12px] uppercase tracking-[0.14em] text-[#5c5f66] font-semibold">CivBro</span>
      <button
        class="text-[#909296] hover:text-[#e5e7eb] p-1.5 rounded-lg hover:bg-[#25262b] transition-colors"
        onclick={onClose}
        aria-label="Close"
      >
        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="5" x2="19" y2="19"/><line x1="19" y1="5" x2="5" y2="19"/></svg>
      </button>
    </div>

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
    <div class="flex-1 flex overflow-hidden min-h-0">
    <!-- LEFT: enlarged viewer + carousel + description -->
    <div class="flex-1 flex flex-col overflow-y-auto min-w-0">
      <div class="p-4 pb-3" data-testid="viewer">
        {#if heroImages.length > 0}
          <div class="relative">
            <div class="grid grid-cols-4 gap-3">
              {#each heroImages as img, i}
                <button
                  class="group relative aspect-[3/4] rounded-xl overflow-hidden bg-[#25262b] border transition-all
                    {pageStart + i === activeImg ? 'border-[#228be6] shadow-[0_0_18px_-2px_rgba(34,139,230,0.55)]' : 'border-[#2c2e33] hover:border-[#4a4e55]'}"
                  onclick={() => openLb(pageStart + i)}
                >
                  {#if img.type === "video"}
                    <video use:lazyVideo={img.url} loop muted playsinline preload="none" class="w-full h-full object-cover"></video>
                  {:else}
                    <img alt="" class="w-full h-full object-cover" decoding="async" use:batchImg={{ src: imgSrc(img, 450), priority: i }} />
                  {/if}
                </button>
              {/each}
            </div>

            {#if galleryImages.length > 4}
              <button
                class="absolute left-2 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-[#1a1b1e]/80 backdrop-blur border border-[#2c2e33] text-[#e5e7eb] hover:bg-[#228be6] hover:border-[#228be6] disabled:opacity-25 disabled:pointer-events-none flex items-center justify-center shadow-lg transition-all"
                onclick={pagePrev}
                disabled={activeImg === 0}
                aria-label="Previous image"
              >
                <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
              </button>
              <button
                class="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-[#1a1b1e]/80 backdrop-blur border border-[#2c2e33] text-[#e5e7eb] hover:bg-[#228be6] hover:border-[#228be6] disabled:opacity-25 disabled:pointer-events-none flex items-center justify-center shadow-lg transition-all"
                onclick={pageNext}
                disabled={activeImg >= galleryImages.length - 1}
                aria-label="Next image"
              >
                <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
              </button>
              <div class="absolute bottom-2 right-2 text-[11px] text-[#e5e7eb] bg-[#1a1b1e]/80 backdrop-blur px-2.5 py-1 rounded-full border border-[#2c2e33]">{activeImg + 1} / {galleryImages.length}</div>
            {/if}
          </div>
        {:else}
          <div class="h-[420px] flex items-center justify-center text-[#5c5f66] text-sm border border-[#2c2e33] rounded-xl">No preview images</div>
        {/if}
      </div>

      <!-- carousel -->
      {#if galleryImages.length > 1}
        <div class="border-t border-[#2c2e33] bg-[#161719]" data-testid="carousel">
          <div bind:this={carouselEl} use:hscroll class="flex gap-2 overflow-x-auto px-5 py-3 civ-hscroll">
            {#each galleryImages as img, i}
              <button
                class="shrink-0 w-16 h-20 rounded-lg overflow-hidden border-2 transition-all
                  {i === activeImg ? 'border-[#228be6] opacity-100' : 'border-transparent opacity-45 hover:opacity-80'}"
                onclick={() => (activeImg = i)}
                title={`Image ${i + 1}`}
              >
                {#if img.type === "video"}
                  <video use:lazyVideo={img.url} muted playsinline loop preload="none" class="w-full h-full object-cover"></video>
                {:else}
                  <img alt="" class="w-full h-full object-cover" decoding="async" use:batchImg={{ src: imgSrc(img, 128), priority: 100 + i }} />
                {/if}
              </button>
            {/each}
          </div>
        </div>
      {/if}

      <!-- description -->
      <div class="border-t border-[#2c2e33] px-8 py-7 space-y-7">
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
            {@html html}
          </div>
        {/snippet}

        {#if selectedVersion?.description}
          <div>
            <h3 class="text-[11px] font-semibold text-[#909296] uppercase tracking-[0.1em] mb-3">About this version{selectedVersion?.name ? ` — ${selectedVersion.name}` : ""}</h3>
            {@render prose(selectedVersion.description)}
          </div>
        {/if}
        {#if model.description}
          <div>
            {#if selectedVersion?.description}
              <h3 class="text-[11px] font-semibold text-[#909296] uppercase tracking-[0.1em] mb-3">Description</h3>
            {/if}
            {@render prose(model.description)}
          </div>
        {/if}
        {#if !selectedVersion?.description && !model.description}
          <p class="text-[#5c5f66] italic text-[14px]">No description provided.</p>
        {/if}
            </div>
          </div>

    <!-- RIGHT: model name + versions + download + details -->
    <aside class="w-[360px] shrink-0 border-l border-[#2c2e33] flex flex-col overflow-y-auto bg-[#1a1b1e]" data-testid="right-col">
      <div class="p-5 flex flex-col gap-5">
        <!-- model name + stats -->
        <div>
          <h1 class="text-[34px] font-bold text-[#c1c2c5] leading-tight tracking-tight">{model.name}</h1>
          <div class="flex items-center gap-3 mt-2.5 text-[14px] text-[#c1c2c5]">
            <span class="inline-flex items-center gap-1" title="Downloads">
              <svg class="w-[16px] h-[16px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 00-6 0v4M5 9h14l1 12H4L5 9z"/></svg>
              {fmtN((model.stats || {}).downloadCount || 0)}
            </span>
            <span class="inline-flex items-center gap-1" title="Likes">
              <svg class="w-[16px] h-[16px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 11v10M15 5l-1 6h5.5a1.5 1.5 0 011.5 1.8l-1.3 6A2 2 0 0117 21H7"/></svg>
              {fmtN((model.stats || {}).thumbsUpCount || 0)}
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
              <span class="text-[11px] text-[#71717a] shrink-0">{fmtN((model.stats || {}).ratingCount || 0)}</span>
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
              {#each versions as ver}
                {@const inst = installedSet.has(ver.id)}
                {@const buzz = (ver as any).availability === 'EarlyAccess' || (ver as any).buzzCost > 0}
                <button
                  style="padding:4px 10px"
                  class="rounded-full text-[14px] font-bold leading-tight transition-colors border inline-flex items-center gap-1.5
                    {selectedVersion?.id === ver.id
                      ? (buzz ? 'bg-[#3a2f0a] text-[#ffd43b] border-[#fab005]' : (inst ? 'bg-[#1971c2] text-white border-[#51cf66]' : 'bg-[#1971c2] text-white border-[#1971c2]'))
                      : (buzz
                          ? 'bg-[#2a2410] text-[#fab005] border-[#fab005]/45 hover:border-[#fab005]'
                          : (inst
                              ? 'bg-[#1e3226] text-[#69db7c] border-[#2f9e44] hover:bg-[#24402f]'
                              : 'bg-[#25262b] text-[#c1c2c5] border-[#2c2e33] hover:bg-[#2c2e33] hover:border-[#4a4e55]'))}"
                  onclick={() => {
                    onSelectVersion(ver);
                    activeImg = 0;
                  }}
                  title={buzz ? "Early Access — requires Buzz" : (inst ? "Installed locally" : ver.name)}
                >
                  {#if inst}
                    <svg class="w-3 h-3 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                  {/if}
                  {ver.name}
                  {#if buzz}
                    <svg class="w-3 h-3 shrink-0" viewBox="0 0 24 24" fill="currentColor" aria-label="Requires Buzz"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                  {/if}
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
                {#each modelFiles as file}
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
                          {fmtBytes(fdl.bytesDownloaded || 0)} / {fmtBytes(fdl.bytesTotal || 0)} · {fdl.progress}%{fmtSpeed(fdl.speed || 0) ? ` · ${fmtSpeed(fdl.speed || 0)}` : ""}{fmtEta(fdl.etaSec || 0) ? ` · ETA ${fmtEta(fdl.etaSec || 0)}` : ""}
                        </div>
                      {/if}
                    </div>
                    <span class="text-[13px] text-[#a1a1aa] font-medium shrink-0">{fmtS(file.sizeKB)}</span>
                    <button
                      class="shrink-0 w-9 h-9 rounded-md flex items-center justify-center transition-colors disabled:opacity-60
                        {(fdl?.status === 'completed' || isInstalled(file.id)) ? 'bg-[#1e3226] text-[#22c55e]' : 'bg-[#3f3f46] hover:bg-[#2563eb] text-[#d4d4d8] hover:text-white'}"
                      onclick={() => download(file)}
                      disabled={isActive(fdl) || (isInstalled(file.id) && fdl?.status !== 'failed' && fdl?.status !== 'gone')}
                      title={isInstalled(file.id) ? "Already downloaded (healthy)" : `Download ${file.name}`}
                      aria-label={isInstalled(file.id) ? "Already installed" : `Download ${file.name}`}
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
                {primaryDl?.status === 'completed' || isInstalled(primaryFile?.id) ? 'bg-[#2f9e44] border-[#37b24d] hover:bg-[#2b8a3e]' : 'bg-[#1d4ed8] border-[#2563eb] hover:bg-[#1a44c2]'}"
              onclick={downloadPrimary}
              disabled={isActive(primaryDl) || modelFiles.length === 0 || (isInstalled(primaryFile?.id) && primaryDl?.status !== "failed" && primaryDl?.status !== "gone")}
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
                <span>{fmtBytes(primaryDl.bytesDownloaded || 0)} / {fmtBytes(primaryDl.bytesTotal || 0)}</span>
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
              {#each componentFiles as file}
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
                        {fmtBytes(cfl.bytesDownloaded || 0)} / {fmtBytes(cfl.bytesTotal || 0)} · {cfl.progress}%{fmtSpeed(cfl.speed || 0) ? ` · ${fmtSpeed(cfl.speed || 0)}` : ""}{fmtEta(cfl.etaSec || 0) ? ` · ETA ${fmtEta(cfl.etaSec || 0)}` : ""}
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
              {#each deps as dep}
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
                        {fmtBytes(ddl.bytesDownloaded || 0)} / {fmtBytes(ddl.bytesTotal || 0)} · {ddl.progress}%{fmtSpeed(ddl.speed || 0) ? ` · ${fmtSpeed(ddl.speed || 0)}` : ""}{fmtEta(ddl.etaSec || 0) ? ` · ETA ${fmtEta(ddl.etaSec || 0)}` : ""}
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
              <span class="text-[#909296]">Downloads</span><span class="text-[#c1c2c5]">{fmtN((model.stats || {}).downloadCount || 0)}</span>
            </div>
            {#if review}
              <div class="flex justify-between px-3 py-2 border-b border-[#2c2e33] gap-2">
                <span class="text-[#909296]">Reviews</span>
                <span class="{review.positive ? 'text-[#51cf66]' : 'text-[#ffa94d]'} font-medium text-right">{review.label} <span class="text-[#909296] font-normal">({fmtN(review.total)})</span></span>
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
                <span class="text-[#909296]">Steps</span><span class="text-[#c1c2c5] font-medium">{fmtN(selectedVersion.steps!)}</span>
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
          </div>
        </div>

        <!-- trigger words -->
        {#if selectedVersion?.trainedWords?.length}
          <div>
            <h3 class="text-[11px] font-semibold text-[#909296] uppercase tracking-[0.1em] mb-2">Trigger Words</h3>
            <div class="flex flex-wrap gap-1.5">
              {#each selectedVersion.trainedWords as w}
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

        <!-- tags -->
        {#if modelTags.length}
          <div>
            <h3 class="text-[11px] font-semibold text-[#909296] uppercase tracking-[0.1em] mb-2">Tags</h3>
            <div class="flex flex-wrap gap-1.5" data-testid="tags">
              {#each modelTags as t}
                <button
                  class="px-2.5 py-1 bg-[#25262b] rounded-full text-[11px] text-[#9da4ae] border border-[#2c2e33] uppercase tracking-wide hover:bg-[#2c2e33] hover:text-[#c1c2c5] hover:border-[#4a4e55] cursor-pointer transition-colors"
                  onclick={() => searchByTag(t)}
                  title={`Search Civitai for "${t}"`}
                >{t}</button>
              {/each}
            </div>
          </div>
        {/if}

        <!-- creator box -->
        {#if model.creator?.username}
          <div class="rounded-lg bg-[#25262b] border border-[#2c2e33] overflow-hidden" data-testid="creator">
            <div class="h-12 bg-gradient-to-r from-[#1e3a8a]/40 via-[#7c3aed]/20 to-[#25262b]"></div>
            <div class="p-4 pt-0 -mt-6">
              <div class="flex items-start gap-3">
                {#if model.creator.image}
                  <img class="w-14 h-14 rounded-full object-cover shrink-0 ring-[3px] ring-[#25262b]" src={model.creator.image} alt="" />
                {:else}
                  <div class="w-14 h-14 rounded-full bg-gradient-to-br from-[#4a4e55] to-[#2c2e33] flex items-center justify-center text-[20px] font-semibold text-white shrink-0 ring-[3px] ring-[#25262b]">{model.creator.username.charAt(0).toUpperCase()}</div>
                {/if}
                <div class="min-w-0 flex-1 pt-0.5">
                  <p class="text-[16px] font-bold text-white truncate leading-tight">{model.creator.username}</p>
                  {#if selectedVersion?.creator?.createdAt}
                    <p class="text-[11px] text-[#71717a] mt-0.5">Joined {fmtAgo(selectedVersion.creator.createdAt)}</p>
                  {/if}
                </div>
              </div>
              <div class="flex items-center gap-4 mt-3 text-[12px] text-[#a1a1aa]">
                <span class="inline-flex items-center gap-1.5">
                  <svg class="w-[14px] h-[14px] text-[#3b82f6]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 00-6 0v4M5 9h14l1 12H4L5 9z"/></svg>
                  <span class="text-white font-semibold">{fmtN((model.stats || {}).downloadCount || 0)}</span> Downloads
                </span>
                <span class="inline-flex items-center gap-1.5">
                  <svg class="w-[14px] h-[14px] text-[#ef4444]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 11v10M15 5l-1 6h5.5a1.5 1.5 0 011.5 1.8l-1.3 6A2 2 0 0117 21H7"/></svg>
                  <span class="text-white font-semibold">{fmtN((model.stats || {}).thumbsUpCount || 0)}</span> Likes
                </span>
              </div>
              <a
                class="mt-3 w-full inline-flex items-center justify-center gap-1.5 text-[12px] font-semibold text-white bg-[#1971c2] hover:bg-[#1a7cd9] rounded-lg px-3 py-2 transition-colors"
                href={`https://civitai.com/user/${encodeURIComponent(model.creator.username)}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                <svg class="w-[16px] h-[16px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/></svg>
                View profile on Civitai
              </a>
            </div>
          </div>
        {/if}
      </div>
    </aside>
    </div>
  </div>
</div>

<!-- lightbox -->
{#if showLb}
  <div
    class="fixed inset-0 z-[60] bg-black flex items-center justify-center"
    onclick={() => (showLb = false)}
    onkeydown={(e) => { if (e.key === 'Escape') showLb = false; }}
    role="dialog"
    aria-modal="true"
    tabindex="-1"
  >
    <button
      class="absolute top-4 right-4 text-white/40 hover:text-white z-10 w-10 h-10 rounded-full bg-white/5 hover:bg-white/10 flex items-center justify-center"
      onclick={() => (showLb = false)}
      aria-label="Close"
    >
      <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="5" x2="19" y2="19"/><line x1="19" y1="5" x2="5" y2="19"/></svg>
    </button>
    {#if galleryImages.length > 1}
      <button
        class="absolute left-4 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full bg-white/5 hover:bg-white/10 text-white flex items-center justify-center transition-all z-10 {lbIdx === 0 ? 'opacity-20' : ''}"
        onclick={(e) => {
          e.stopPropagation();
          prevLb();
        }}
        aria-label="Previous image"
      >
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
      </button>
      <button
        class="absolute right-4 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full bg-white/5 hover:bg-white/10 text-white flex items-center justify-center transition-all z-10 {lbIdx >= galleryImages.length - 1 ? 'opacity-20' : ''}"
        onclick={(e) => {
          e.stopPropagation();
          nextLb();
        }}
        aria-label="Next image"
      >
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
      </button>
      <div class="absolute bottom-6 left-1/2 -translate-x-1/2 text-sm text-white/30">{lbIdx + 1}/{galleryImages.length}</div>
    {/if}
    {#if galleryImages[lbIdx]?.type === "video"}
      <video src={galleryImages[lbIdx].url} autoplay loop muted playsinline controls class="max-w-[92vw] max-h-[92vh] object-contain z-0 rounded-lg"></video>
    {:else if galleryImages[lbIdx]}
      <img alt="" class="max-w-[92vw] max-h-[92vh] object-contain z-0 rounded-lg" decoding="async" use:batchImg={{ src: imgSrc(galleryImages[lbIdx], 1600), priority: -100 }} />
    {/if}
  </div>
{/if}
