<script lang="ts">
  import { appState } from "./stores.svelte.ts";
  import type { CivitaiModel, ModelVersion, ModelFile } from "./stores.svelte.ts";
  import { getModel } from "./api.ts";
  import { getCardDownloadStatus } from "./card-download-status";
  import { isNsfwImage } from "./browse";
  import { fmtCount } from "./format.ts";
  import { subdirForType } from "./paths.ts";
  import DownloadButton from "./DownloadButton.svelte";

  interface Props {
    model: CivitaiModel;
    onSelect: () => void;
  }

  let { model, onSelect }: Props = $props();

  // Civitai renders a gradient border + glow on cards whose creator equipped a
  // "cosmetic" (content decoration). It's per-model (not per-base-model): the
  // gradient is model.cosmetic.cssFrame. Cards without a cosmetic get no border,
  // exactly like Civitai. Applied inline via padding-box/border-box.
  let frame = $derived(model.cosmetic?.cssFrame || "");
  let frameGlow = $derived(model.cosmetic?.glow ?? false);
  let lightTextureStyle = $derived.by(() => {
    const cosmetic = model.cosmetic;
    if (cosmetic?.type !== "holiday-lights" || !cosmetic.textureUrl) return "";
    const width = cosmetic.textureWidth || 14;
    const height = cosmetic.textureHeight || 14;
    const colors: Record<string, string> = {
      green: "#4f7a43",
      yellow: "#d5a921",
      red: "#b83d3d",
      blue: "#366eb5",
      white: "#d9e2ec",
    };
    const color = colors[(cosmetic.color || "").toLowerCase()] || "#d9e2ec";
    return `--light-texture:url('${cosmetic.textureUrl}');--light-size:${width}px ${height}px;--light-brightness:${cosmetic.brightness ?? 1};--light-color:${color};`;
  });
  let cardStyle = $derived.by(() => {
    const base = "aspect-ratio:7/9; content-visibility:auto; contain-intrinsic-size:285px 366px;";
    if (frame) {
      const glow = frameGlow ? `box-shadow:0 0 4px 1px rgba(255,255,255,0.12);` : "";
      return `${base}border:6px solid transparent; border-radius:8px; background: linear-gradient(#1a1b1e,#1a1b1e) padding-box, ${frame} border-box;${glow}`;
    }
    return base;
  });

  let imageRevealed = $state(false);
  let imageError = $state(false);
  let dlBtnBusy = $state(false);

  // Model has at least one healthy local file — check the persistent installed-model
  // set (populated from disk-sidecar scan at startup). Also consider any in-flight
  // completed download from the current session.
  let modelHasInstalled = $derived.by(() => {
    if (appState.installedModelIds.has(model.id)) return true;
    const dls = appState.downloads;
    for (const id in dls) {
      if (dls[id].modelId === model.id && dls[id].status === "completed") return true;
    }
    return false;
  });

  // Derive card-level download status from the global downloads map.
  let cardDl = $derived.by(() => {
    const dls = appState.downloads;
    for (const id in dls) {
      if (dls[id].modelId === model.id) return dls[id];
    }
    return null;
  });

  let dlStatus = $derived.by(() => getCardDownloadStatus({
    activeStatus: cardDl?.status ?? null,
    busy: dlBtnBusy,
    installed: modelHasInstalled,
    buzzRequired: model.hasBuzz === true,
    buzzUnlocked: appState.unlockedBuzzModelIds.has(model.id),
    earlyAccess: model.availability === "EarlyAccess",
    modelNsfw: model.nsfw === true,
    nsfwBrowsing: appState.filters.nsfw,
    apiKeyConfigured: appState.apiKeyConfigured,
  }));

  let dlLabel = $derived.by(() => {
    if (dlStatus === "active") return "Click to cancel download";
    if (dlStatus === "buzzLocked") return "Buzz required — purchase on civitai.com";
    if (dlStatus === "buzzUnlocked") return "Buzz purchase unlocked — click to download";
    if (dlStatus === "apikeyLocked") return "API key required — add one in sidebar";
    if (dlStatus === "installed" || dlStatus === "completed") return "Click to delete local copy";
    return `Download ${model.name}`;
  });

  const MODELS_ROOT = $derived(appState.config?.modelsRoot || "");
  const DIR_MAP = $derived(appState.config?.frontendDirMap || {});
  function subDir(mt: string): string { return subdirForType(mt, DIR_MAP); }

  let cancelRetry = $state(false);

  async function awaitDownload(id: string): Promise<string> {
    const MAX_WAIT_MS = 300_000;
    let elapsed = 0;
    while (elapsed < MAX_WAIT_MS) {
      if (cancelRetry) return "cancelled";
      await new Promise((r) => setTimeout(r, 500));
      elapsed += 500;
      const dl = appState.downloads[id];
      if (!dl) return "gone";
      if (dl.status === "completed") return "completed";
      if (dl.status === "failed") return "failed";
      if (dl.status === "cancelled") return "cancelled";
    }
    return "timeout";
  }

  function removeDownloadEntry(id: string) {
    const d = { ...appState.downloads };
    delete d[id];
    appState.downloads = d;
    appState.downloadOrder = appState.downloadOrder.filter((x) => x !== id);
  }

  async function cardDownload(e: Event) {
    e.stopPropagation();
    if (dlStatus === "buzzLocked" || dlStatus === "apikeyLocked") {
      window.open(`https://civitai.com/models/${model.id}`, "_blank");
      return;
    }
    // If already downloading, cancel it. If installed, delete the local file.
    if (cardDl && (cardDl.status === "pending" || cardDl.status === "queued" || cardDl.status === "downloading")) {
      cancelRetry = true;
      const dls = appState.downloads;
      for (const id in dls) {
        if (dls[id].modelId === model.id && (dls[id].status === "pending" || dls[id].status === "queued" || dls[id].status === "downloading")) {
          try {
            const api = await import("./api");
            await api.deleteDownload(id);
        } catch (e) {
          console.warn("[CivBro] cardDownload cancel failed:", e);
          }
        }
      }
      return;
    }
    if (modelHasInstalled) {
      if (!confirm(`Delete local copy of ${model.name || "this model"} from disk?`)) return;
      try {
        const api = await import("./api");
        await api.deleteLocalModel(model.id);
      } catch (e) {
        console.debug("[CivBro] cardDownload deleteLocalModel failed:", e);
      }
      return;
    }
    if (dlBtnBusy) return;
    cancelRetry = false;
    dlBtnBusy = true;
    try {
      const detail: any = await getModel(model.id);
      const versions: ModelVersion[] = detail?.modelVersions || detail?.versions || [];
      if (!versions.length) { dlBtnBusy = false; return; }

      const sorted = [...versions].sort((a, b) => {
        const da = a.createdAt ? Date.parse(a.createdAt) : 0;
        const db = b.createdAt ? Date.parse(b.createdAt) : 0;
        return db - da;
      });
      const gated = (v: ModelVersion) =>
        (v as any).availability === "EarlyAccess" || (v as any).buzzCost > 0;
      const gatedList = sorted.filter((v) => gated(v));
      const pubList = sorted.filter((v) => !gated(v));
      const candidates = [...gatedList, ...pubList];

      const dir = `${MODELS_ROOT}/${subDir(detail?.modelType || detail?.type || "")}`;

      for (const v of candidates) {
        if (cancelRetry) break;
        const fs = (v.files || []) as ModelFile[];
        const pf = fs.find((f) => f.primary) || fs[0];
        if (!pf?.downloadUrl) continue;
        const dlId = await appState.queueDownload({
          modelId: model.id,
          versionId: v.id,
          fileId: pf.id,
          downloadUrl: pf.downloadUrl!,
          downloadDir: dir,
          fileName: pf.name,
          fileType: pf.type,
          modelType: detail?.modelType || detail?.type || model.type,
          sizeKB: pf.sizeKB,
        });
        if (!dlId) continue;

        const result = await awaitDownload(dlId);

        if (result === "completed") break;

        const errMsg = (appState.downloads[dlId]?.error || "").toLowerCase();
        removeDownloadEntry(dlId);

        if (result === "cancelled") break;
        if (!errMsg.includes("buzz") && !errMsg.includes("unlock")) break;
      }
    } catch (e) {
      console.debug("[CivBro] cardDownload failed:", e);
    }
    dlBtnBusy = false;
  }

  // Blur is based on the PREVIEW IMAGE's nsfwLevel (what Civitai actually blurs),
  // not the model-level nsfw flag — so an NSFW model with a SFW cover image isn't blurred.
  function primaryImageObj(): any {
    if (model.images && model.images.length > 0) return model.images[0];
    if (model.modelVersions && model.modelVersions.length > 0) {
      const ver = model.modelVersions[0];
      if (ver.images && ver.images.length > 0) return ver.images[0];
    }
    return null;
  }
  let shouldBlur = $derived(appState.nsfwBlurEnabled && isNsfwImage(primaryImageObj() || {}) && !imageRevealed);

  function getPrimaryImage(): string {
    if (model.images && model.images.length > 0) {
      return model.images[0].url;
    }
    if (model.modelVersions && model.modelVersions.length > 0) {
      const ver = model.modelVersions[0];
      if (ver.images && ver.images.length > 0) {
        return ver.images[0].url;
      }
    }
    return "";
  }

  function getPrimaryImageType(): string {
    if (model.images && model.images.length > 0) {
      return model.images[0].type || "image";
    }
    if (model.modelVersions && model.modelVersions.length > 0) {
      const ver = model.modelVersions[0];
      if (ver.images && ver.images.length > 0) {
        return ver.images[0].type || "image";
      }
    }
    return "image";
  }

  let imageUrl = $derived(getPrimaryImage());

  let downloadCount = $derived(
    model.stats?.downloadCount != null
      ? fmtCount(model.stats.downloadCount)
      : ""
  );

  let likes = $derived((model.stats as any)?.thumbsUpCount || (model.stats as any)?.likes || 0);
  let collections = $derived((model.stats as any)?.favoriteCount || 0);
  let comments = $derived((model.stats as any)?.commentCount || 0);
  let buzz = $derived((model.stats as any)?.tippedAmountCount || 0);

  // Model-family pill: "Checkpoint | IL, XL, [pony] +2" — Civitai-style short
  // codes (IL = Illustrious, XL = SDXL, an inline unicorn SVG = Pony, etc).
  // Populated lazily from tRPC extras (model.baseModels).
  function baseCode(b: string): { pony?: boolean; label?: string } {
    const s = (b || "").toLowerCase();
    if (s.includes("pony")) return { pony: true };
    if (s.includes("illustrious")) return { label: "IL" };
    if (s.includes("noob")) return { label: "NAI" };
    if (s.includes("sdxl") || s.includes("sd xl")) return { label: "XL" };
    if (s.includes("sd 1.5") || s.includes("sd1.5")) return { label: "1.5" };
    if (s.includes("sd 3")) return { label: "SD3" };
    if (s.includes("sd 2") || s.includes("sd2")) return { label: "2.x" };
    if (s.includes("flux.2") || s.includes("flux2")) return { label: "F2" };
    if (s.includes("flux")) return { label: "F1" };
    if (s.includes("hidream")) return { label: "HiD" };
    if (s.includes("hunyuan")) return { label: "HY" };
    if (s.includes("qwen")) return { label: "Qwen" };
    if (s.includes("krea")) return { label: "KR2" };
    if (s.includes("anima")) return { label: "ANI" };
    if (s.includes("z-image") || s.includes("zimage") || s.includes("z image")) return { label: "ZIT" };
    if (s.includes("chroma")) return { label: "Chroma" };
    if (s.includes("wan")) return { label: "Wan" };
    if (s.includes("cascade")) return { label: "SC" };
    if (s.includes("aura")) return { label: "Aura" };
    return { label: b.length > 4 ? b.slice(0, 4) : b };
  }
  let typeLabel = $derived(model.type || "");
  const FAMILY_MAX = 3;
  let familyAll = $derived.by(() => {
    const fams = (model.baseModels && model.baseModels.length)
      ? model.baseModels
      : (model.baseModel ? [model.baseModel] : []);
    const seen = new Set<string>();
    const out: { pony?: boolean; label?: string }[] = [];
    for (const f of fams) {
      const c = baseCode(f);
      const key = c.pony ? "pony" : (c.label || "");
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push(c);
    }
    return out;
  });
  let familyItems = $derived(familyAll.slice(0, FAMILY_MAX));
  let familyOverflow = $derived(Math.max(0, familyAll.length - FAMILY_MAX));

  // Early Access pill shows while the EA window is still open; "Updated" shows
  // when a model was (re)published in the last 48h but created earlier.
  let isEarlyAccess = $derived.by(() => {
    if (model.availability === "EarlyAccess") return true;
    if (model.hasBuzz) return true;
    const d = model.earlyAccessDeadline;
    if (d) {
      const t = Date.parse(d);
      return isNaN(t) || t > Date.now();
    }
    return false;
  });
  let isUpdated = $derived.by(() => {
    const pub = model.publishedAt ? Date.parse(model.publishedAt) : NaN;
    if (isNaN(pub)) return false;
    const now = Date.now();
    const DAY2 = 48 * 3600 * 1000;
    if (now - pub > DAY2) return false;
    const cre = model.createdAt ? Date.parse(model.createdAt) : NaN;
    if (!isNaN(cre) && now - cre <= DAY2) return false;
    return true;
  });

  // Uploader nameplate cosmetic (gradient or solid colour on the username).
  let nameStyle = $derived.by(() => {
    const np = model.nameplate;
    if (np?.gradient) return `background:${np.gradient};-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:transparent;`;
    if (np?.color) return `color:${np.color};`;
    return "";
  });

  function handleClick() {
    if (shouldBlur) {
      imageRevealed = true;
      return;
    }
    onSelect();
  }

  function handleImageError() {
    imageError = true;
  }

  let videoPlaying = $state(false);

  // Video previews autoplay while the card is in (or near) the viewport and pause
  // when it leaves — matching Civitai. `preload="metadata"` makes the element show
  // the clip's own first frame as a placeholder (with the ▶ indicator) until it
  // starts playing. Only near-viewport clips ever load, so the grid stays light.
  function bgAutoVideo(node: HTMLVideoElement, src: string) {
    // Set src immediately so the first frame / poster shows at page load.
    // Only play/pause is gated by viewport visibility.
    if (src && !node.src) node.src = src;

    let inView = false;
    const updatePlaying = () => {
      videoPlaying = !node.paused;
    };
    const play = () => {
      if (!inView) return;
      node.play?.().then(updatePlaying).catch(() => {});
    };
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        inView = e.isIntersecting;
        if (inView) {
          play();
        } else {
          videoPlaying = false;
          node.pause?.();
        }
      }
    }, { rootMargin: "400px" });
    io.observe(node);
    const handlePause = () => { videoPlaying = false; };
    node.addEventListener("playing", updatePlaying);
    node.addEventListener("pause", handlePause);
    node.addEventListener("canplay", play);
    node.addEventListener("loadeddata", play);

    return {
      destroy() {
        io.disconnect();
        node.removeEventListener("canplay", play);
        node.removeEventListener("loadeddata", play);
        node.removeEventListener("playing", updatePlaying);
        node.removeEventListener("pause", handlePause);
        node.pause?.();
      },
    };
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions, a11y_click_events_have_key_events -->
<div
  class="civ-card group relative overflow-clip cursor-pointer"
  style={`${cardStyle}${lightTextureStyle}`}
  onclick={handleClick}
  data-testid="model-card"
  data-base-model={model.baseModel || ""}
  data-cosmetic={frame ? "1" : "0"}
>
  {#if lightTextureStyle}
    <div class="holiday-lights" aria-hidden="true"></div>
  {/if}

  {#if imageUrl && !imageError}
    {#if getPrimaryImageType() === "video"}
      <video
        class="civ-card-media absolute inset-0 w-full h-full object-cover object-top transition-all duration-300
          {shouldBlur ? 'blur-[12px] scale-110' : 'blur-0 scale-100'}"
        use:bgAutoVideo={imageUrl}
        poster={model.poster || undefined}
        loop
        muted
        playsinline
        preload="metadata"
        onerror={handleImageError}
      ></video>
      {#if !videoPlaying}
        <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div class="w-11 h-11 rounded-full bg-black/45 flex items-center justify-center">
            <svg class="w-5 h-5 text-white ml-0.5" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
          </div>
        </div>
      {/if}
    {:else}
      <img
        class="civ-card-media absolute inset-0 w-full h-full object-cover object-top transition-all duration-300
          {shouldBlur ? 'blur-[12px] scale-110' : 'blur-0 scale-100'}"
        src={imageUrl}
        alt={model.name}
        loading="lazy"
        decoding="async"
        onerror={handleImageError}
      />
    {/if}
  {:else}
    <div class="absolute inset-0 bg-[#1a1b1e] flex items-center justify-center">
      <div class="text-gray-500 text-2xl">?</div>
    </div>
  {/if}

  {#if shouldBlur}
    <div
      class="absolute inset-0 bg-black/30 flex flex-col items-center justify-center gap-2 cursor-pointer"
      onclick={(e) => { e.stopPropagation(); imageRevealed = true; }}
      onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.stopPropagation(); imageRevealed = true; } }}
      role="button"
      tabindex="0"
      aria-label="Reveal NSFW content"
    >
      <span class="text-white text-xs font-medium bg-red-600/80 px-2 py-1 rounded-full">
        NSFW
      </span>
      <span class="text-gray-300 text-xs">Click to reveal</span>
    </div>
  {/if}

  <!-- type + base-model family pill (top-left): translucent, non-blurred, wraps -->
  <div class="absolute top-2.5 left-2.5 flex flex-wrap items-start gap-1.5 pr-12 pointer-events-none z-0" style="max-width:calc(100% - 48px)">
    {#if typeLabel}
      <span class="inline-flex flex-wrap items-center text-[14px] font-bold uppercase tracking-wide text-white bg-black/45 rounded-full" style="padding:4px 10px;line-height:18px">
        <span>{typeLabel}</span>
        {#if familyItems.length}
          <span class="opacity-30">&nbsp;|&nbsp;</span>
          {#each familyItems as f, i (f.label || 'family-' + i)}
            {#if i > 0}<span class="opacity-50">,&nbsp;</span>{/if}
            {#if f.pony}
              <svg class="w-[18px] h-[18px] inline-block -my-px" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" role="img" aria-label="Pony"><title>Pony</title><path d="M7 10l-.85 8.507a1.357 1.357 0 0 0 1.35 1.493h.146a2 2 0 0 0 1.857 -1.257l.994 -2.486a2 2 0 0 1 1.857 -1.257h1.292a2 2 0 0 1 1.857 1.257l.994 2.486a2 2 0 0 0 1.857 1.257h.146a1.37 1.37 0 0 0 1.364 -1.494l-.864 -9.506h-8c0 -3 -3 -5 -6 -5l-3 6l2 2l3 -2z"/><path d="M22 14v-2a3 3 0 0 0 -3 -3"/></svg>
            {:else}
              <span class="normal-case">{f.label}</span>
            {/if}
          {/each}
          {#if familyOverflow > 0}<span class="opacity-70 ml-1">+{familyOverflow}</span>{/if}
        {/if}
      </span>
    {/if}
    {#if isEarlyAccess}
      <span class="inline-flex items-center text-[14px] font-bold uppercase tracking-wide text-white bg-[#3acd84] rounded-full" style="padding:4px 10px;line-height:18px">Early Access</span>
    {:else if isUpdated}
      <span class="inline-flex items-center text-[14px] font-bold uppercase tracking-wide text-white bg-[#3acd84] rounded-full" style="padding:4px 10px;line-height:18px">Updated</span>
    {/if}
  </div>

  <!-- download button top-right -->
  <div class="absolute top-2 right-2 z-10">
    <DownloadButton status={dlStatus} label={dlLabel} onclick={cardDownload} />
  </div>

  <div
    class="creator-strip absolute bottom-0 left-0 right-0 pointer-events-none"
  >
    <div class="flex items-center gap-2 mb-1">
      <div class="relative shrink-0" style="width:38.4px;height:38.4px;">
        {#if model.creator?.image}
          <img
            class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full object-cover border border-white/25"
            style="width:38.4px;height:38.4px;"
            src={model.creator.image}
            alt={model.creator.username}
          />
        {:else}
          <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#2a2b30] flex items-center justify-center text-[14px] text-gray-300 border border-white/25" style="width:38.4px;height:38.4px;">
            {model.creator?.username?.charAt(0)?.toUpperCase() || "?"}
          </div>
        {/if}
        {#if model.avatarDeco}
          <div
            class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none"
            style="width:45.6px;height:45.6px;"
          >
            <img
              style="width:100%;height:100%;object-fit:contain;"
              src={model.avatarDeco}
              alt=""
              onerror={(e) => ((e.currentTarget as HTMLImageElement).style.opacity = '0')}
            />
          </div>
        {/if}
      </div>
      <span
        class="text-[15px] font-medium truncate"
        style="{nameStyle || 'color:rgb(254,254,254)'};text-shadow:0 1px 2px rgba(0,0,0,0.95)"
      >
        {model.creator?.username || "Unknown"}
      </span>
      {#if model.badge}
        <img
          class="h-[33.6px] w-auto shrink-0"
          style="object-fit:contain;"
          src={model.badge}
          alt=""
          onerror={(e) => ((e.currentTarget as HTMLImageElement).style.display = 'none')}
        />
      {/if}
    </div>

    <p class="text-[21px] font-bold text-white leading-[26px] line-clamp-2" style="text-shadow:0 1px 2px rgba(0,0,0,0.95)">{model.name}</p>

    <div class="flex items-center gap-1.5 mt-1.5 flex-wrap">
      <div class="inline-flex items-center gap-2 bg-black/35 rounded-full text-white/90 text-[14px] font-bold" style="padding:4px 10px;line-height:18px">
        {#if downloadCount}
          <span class="inline-flex items-center gap-0.5">
            <svg class="w-[16px] h-[16px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            {downloadCount}
          </span>
        {/if}
        {#if collections > 0}
          <span class="inline-flex items-center gap-0.5">
            <svg class="w-[16px] h-[16px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/></svg>
            {fmtCount(collections)}
          </span>
        {/if}
        {#if comments > 0}
          <span class="inline-flex items-center gap-0.5">
            <svg class="w-[16px] h-[16px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z"/></svg>
            {fmtCount(comments)}
          </span>
        {/if}
        {#if buzz > 0}
          <span class="inline-flex items-center gap-0.5">
            <svg class="w-[14px] h-[14px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
            {fmtCount(buzz)}
          </span>
        {/if}
      </div>
      {#if likes > 0}
        <div class="inline-flex items-center gap-1 bg-black/35 rounded-full text-[#fd7f38] text-[14px] font-bold" style="padding:4px 10px;line-height:18px">
          <svg class="w-[14px] h-[14px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3zM7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3"/></svg>
          {fmtCount(likes)}
        </div>
      {/if}
    </div>
  </div>
</div>

<style>
  .civ-card {
    isolation: isolate;
    transition: transform 260ms cubic-bezier(.2,.8,.2,1), box-shadow 260ms ease;
  }

  .creator-strip {
    padding: 8px 14px 14px;
  }

  .civ-card::after {
    content: "";
    position: absolute;
    inset: 0;
    z-index: 21;
    padding: 3px;
    border-radius: inherit;
    opacity: 0;
    --halo-angle: 0deg;
    background: conic-gradient(from var(--halo-angle), transparent 0 8%, #55d7ff 15%, #fff 23%, #a855f7 34%, transparent 45% 58%, #ffd166 68%, #ff4ecd 78%, #4de7ff 90%, transparent 100%);
    filter: saturate(1.5) brightness(1.4) drop-shadow(0 0 10px rgb(85 215 255 / .9));
    pointer-events: none;
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    -webkit-mask-composite: xor;
    mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    mask-composite: exclude;
  }

  .civ-card:hover {
    z-index: 30;
    transform: translateY(-10px) scale(1.018);
    box-shadow: 0 20px 34px rgb(0 0 0 / .55), 0 0 28px rgb(78 197 255 / .35);
  }

  .civ-card:hover::after {
    opacity: 1;
    animation: card-halo-spin 1.35s linear infinite;
  }

  @keyframes card-halo-spin {
    to { --halo-angle: 360deg; }
  }

  @property --halo-angle {
    syntax: "<angle>";
    inherits: false;
    initial-value: 0deg;
  }

  .holiday-lights {
    position: absolute;
    inset: 0;
    z-index: 20;
    padding: 6px;
    border-radius: 8px;
    filter: brightness(var(--light-brightness));
    pointer-events: none;
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    -webkit-mask-composite: xor;
    mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    mask-composite: exclude;
  }

  .holiday-lights::before {
    content: "";
    position: absolute;
    inset: 0;
    background: var(--light-color);
    -webkit-mask-image: var(--light-texture);
    -webkit-mask-repeat: repeat;
    -webkit-mask-size: var(--light-size);
    mask-image: var(--light-texture);
    mask-repeat: repeat;
    mask-size: var(--light-size);
  }

  @media (prefers-reduced-motion: reduce) {
    .civ-card, .civ-card::after { transition: none; animation: none !important; }
  }
</style>
