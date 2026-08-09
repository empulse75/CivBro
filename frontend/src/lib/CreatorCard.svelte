<script lang="ts">
  import type { CivitaiModel, ModelVersion } from "./stores/types";
  import { fmtCount } from "./format";

  interface Props {
    model: CivitaiModel;
    selectedVersion: ModelVersion | null;
  }

  let { model, selectedVersion }: Props = $props();

  const username = $derived(model.creator?.username || "Unknown");
  const nameStyle = $derived.by(() => {
    if (model.nameplate?.gradient) {
      return `background:${model.nameplate.gradient};-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:transparent;`;
    }
    return model.nameplate?.color ? `color:${model.nameplate.color};` : "";
  });
  const joined = $derived.by(() => {
    const value = selectedVersion?.creator?.createdAt;
    if (!value) return "";
    try {
      return `Joined ${new Date(value).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}`;
    } catch {
      return "";
    }
  });
  const metrics = $derived([
    { label: "Downloads", value: (model.stats || {}).downloadCount || 0, icon: "download" },
    { label: "Likes", value: (model.stats || {}).thumbsUpCount || 0, icon: "like" },
    { label: "Reviews", value: (model.stats || {}).ratingCount || 0, icon: "star" },
  ].filter((metric) => metric.value > 0));
</script>

<div class="creator-card" data-testid="creator">
  <div class="creator-card__hero">
    {#if model.profileBackground?.type === "video"}
      <video class="creator-card__background" src={model.profileBackground.url} autoplay loop muted playsinline></video>
    {:else if model.profileBackground}
      <img class="creator-card__background" src={model.profileBackground.url} alt="" />
    {:else}
      <div class="creator-card__background creator-card__background--fallback"></div>
    {/if}
    <div class="creator-card__wash"></div>

    <div class="creator-card__metrics">
      {#each metrics as metric (metric.label)}
        <div class="creator-card__metric" title={metric.label}>
          <span class="creator-card__metric-icon">
            {#if metric.icon === "download"}
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v11m0 0-4-4m4 4 4-4M5 18v2h14v-2"/></svg>
            {:else if metric.icon === "like"}
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 11v10M15 5l-1 6h5.5a1.5 1.5 0 0 1 1.5 1.8l-1.3 6A2 2 0 0 1 17 21H7"/></svg>
            {:else}
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="m12 2 3.1 6.3L22 9.3l-5 4.9 1.2 6.8-6.2-3.2L5.8 21 7 14.2 2 9.3l6.9-1z"/></svg>
            {/if}
          </span>
          <span>{fmtCount(metric.value)}</span>
        </div>
      {/each}
    </div>

    {#if model.badge}
      <img class="creator-card__badge" src={model.badge} alt="Creator badge" />
    {/if}
  </div>

  <div class="creator-card__profile">
    <a class="creator-card__identity" href={`https://civitai.com/user/${encodeURIComponent(username)}`} target="_blank" rel="noopener noreferrer">
      <span class="creator-card__avatar-wrap">
        {#if model.creator?.image}
          <img class="creator-card__avatar" src={model.creator.image} alt={`${username}'s avatar`} />
        {:else}
          <span class="creator-card__avatar creator-card__avatar--fallback">{username.charAt(0).toUpperCase()}</span>
        {/if}
        {#if model.avatarDeco}
          <img class="creator-card__avatar-deco" src={model.avatarDeco} alt="" />
        {/if}
      </span>
      <span class="creator-card__identity-copy">
        <span class="creator-card__name" style={nameStyle}>{username}</span>
        {#if joined}<span class="creator-card__joined">{joined}</span>{/if}
      </span>
    </a>

    <a class="creator-card__profile-link" href={`https://ko-fi.com/${encodeURIComponent(username)}`} target="_blank" rel="noopener noreferrer" title="Buy me a coffee">
      <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M6 2h12v3H6zM5 5h14l1 12H4zm2 1v3h10V6zm-1 5h12v1H6zm1 2h10v2H7zm-1.5 4h13l-1 6H5.5z"/><path d="M18 8h2a2 2 0 0 1 2 2v1a2 2 0 0 1-2 2h-2" fill="none" stroke="currentColor" stroke-width="2"/></svg>
    </a>
  </div>

  <div class="creator-card__footer">
    <a href={`https://ko-fi.com/${encodeURIComponent(username)}`} target="_blank" rel="noopener noreferrer">
      <svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 2h12v3H6zM5 5h14l1 12H4zm2 1v3h10V6zm-1 5h12v1H6zm1 2h10v2H7zm-1.5 4h13l-1 6H5.5z"/><path d="M18 8h2a2 2 0 0 1 2 2v1a2 2 0 0 1-2 2h-2" fill="none" stroke="currentColor" stroke-width="2"/></svg>
      Buy me a coffee
    </a>
  </div>
</div>

<style>
  .creator-card {
    position: relative;
    height: 189px;
    overflow: hidden;
    border: 1px solid #373a40;
    border-radius: 8px;
    background: #25262b;
  }

  .creator-card__hero {
    position: relative;
    height: 145px;
    overflow: hidden;
  }

  .creator-card__background {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .creator-card__background--fallback {
    background:
      radial-gradient(circle at 78% 20%, rgb(59 130 246 / 0.4), transparent 30%),
      radial-gradient(circle at 18% 70%, rgb(124 58 237 / 0.34), transparent 38%),
      linear-gradient(135deg, #172554, #312e81 48%, #25262b);
  }

  .creator-card__wash {
    position: absolute;
    inset: 0;
    background: linear-gradient(180deg, rgb(10 11 14 / 0.08) 0%, rgb(10 11 14 / 0.15) 52%, rgb(10 11 14 / 0.9) 100%);
  }

  .creator-card__metrics {
    position: absolute;
    top: 16px;
    left: 16px;
    display: flex;
    gap: 6px;
    z-index: 2;
  }

  .creator-card__metric {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    min-height: 26px;
    padding: 3px 8px 3px 5px;
    border: 1px solid rgb(255 255 255 / 0.14);
    border-radius: 999px;
    color: #f8fafc;
    background: rgb(22 23 27 / 0.76);
    box-shadow: 0 4px 14px rgb(0 0 0 / 0.24);
    backdrop-filter: blur(7px);
    font-size: 11px;
    font-weight: 700;
  }

  .creator-card__metric-icon {
    display: grid;
    width: 18px;
    height: 18px;
    place-items: center;
    border-radius: 50%;
    color: #dbeafe;
    background: rgb(59 130 246 / 0.22);
  }

  .creator-card__metric-icon svg {
    width: 12px;
    height: 12px;
  }

  .creator-card__badge {
    position: absolute;
    top: 16px;
    right: 16px;
    z-index: 2;
    width: 60px;
    height: 60px;
    object-fit: contain;
    filter: drop-shadow(0 6px 10px rgb(0 0 0 / 0.42));
  }

  .creator-card__profile {
    position: absolute;
    inset: 92px 0 auto;
    z-index: 3;
    display: flex;
    height: 53px;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 8px 16px;
    background: rgb(16 17 19 / 0.4);
    backdrop-filter: blur(10px);
  }

  .creator-card__identity {
    display: flex;
    min-width: 0;
    flex: 1;
    align-items: center;
    gap: 70px;
    color: inherit;
    text-decoration: none;
  }

  .creator-card__avatar-wrap {
    position: absolute;
    top: -12px;
    left: 16px;
    width: 60px;
    height: 60px;
  }

  .creator-card__avatar {
    display: grid;
    width: 60px;
    height: 60px;
    place-items: center;
    border: 3px solid rgb(22 23 27 / 0.92);
    border-radius: 50%;
    object-fit: cover;
    color: white;
    background: #373a40;
    font-size: 20px;
    font-weight: 700;
  }

  .creator-card__avatar-deco {
    position: absolute;
    inset: -9px;
    z-index: 2;
    width: 78px;
    height: 78px;
    max-width: none;
    object-fit: contain;
    pointer-events: none;
  }

  .creator-card__identity-copy {
    display: flex;
    min-width: 0;
    margin-left: 70px;
    flex-direction: column;
  }

  .creator-card__name {
    overflow: hidden;
    color: #fff;
    font-size: 16px;
    font-weight: 750;
    line-height: 20px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .creator-card__joined {
    color: #a1a1aa;
    font-size: 11px;
    line-height: 15px;
  }

  .creator-card__profile-link {
    display: inline-flex;
    height: 32px;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    width: 32px;
    gap: 6px;
    border: 1px solid rgb(245 158 11 / 0.4);
    border-radius: 6px;
    color: #fbbf24;
    background: rgb(180 83 9 / 0.2);
    text-decoration: none;
    transition: background-color 150ms ease, border-color 150ms ease;
  }

  .creator-card__profile-link:hover {
    border-color: #f59e0b;
    background: rgb(245 158 11 / 0.3);
    color: #fcd34d;
  }

  .creator-card__profile-link svg {
    width: 16px;
    height: 16px;
  }

  .creator-card__footer {
    position: absolute;
    inset: auto 0 0;
    z-index: 4;
    display: flex;
    height: 44px;
    align-items: center;
    padding: 6px 16px;
    border-top: 1px solid rgb(55 58 64 / 0.8);
    background: rgb(37 38 43 / 0.4);
    backdrop-filter: blur(10px);
  }

  .creator-card__footer a {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    color: #909296;
    font-size: 11px;
    font-weight: 650;
    text-decoration: none;
    transition: color 150ms ease;
  }

  .creator-card__footer a:hover {
    color: #74c0fc;
  }

  .creator-card__footer svg {
    width: 18px;
    height: 18px;
  }

</style>
