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

<div class="creator-card group" data-testid="creator">
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
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 3v11m0 0-4-4m4 4 4-4M5 18v2h14v-2"/></svg>
            {:else if metric.icon === "like"}
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M7 11v10M15 5l-1 6h5.5a1.5 1.5 0 0 1 1.5 1.8l-1.3 6A2 2 0 0 1 17 21H7"/></svg>
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
    height: 195px;
    overflow: hidden;
    border: 1px solid var(--civ-border, rgba(42, 58, 78, 0.6));
    border-radius: 16px;
    background: var(--civ-panel, #131c29);
    box-shadow: 0 12px 28px rgba(0, 0, 0, 0.3);
    transition: border-color 200ms ease, box-shadow 200ms ease;
  }

  .creator-card:hover {
    border-color: rgba(103, 232, 198, 0.35);
    box-shadow: 0 16px 36px rgba(0, 0, 0, 0.45);
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
      radial-gradient(circle at 78% 20%, rgba(103, 232, 198, 0.3), transparent 35%),
      radial-gradient(circle at 18% 70%, rgba(183, 164, 255, 0.25), transparent 40%),
      linear-gradient(135deg, #0b1018, #131c29 50%, #1a2636);
  }

  .creator-card__wash {
    position: absolute;
    inset: 0;
    background: linear-gradient(180deg, rgba(11, 16, 24, 0.1) 0%, rgba(11, 16, 24, 0.35) 50%, rgba(11, 16, 24, 0.95) 100%);
  }

  .creator-card__metrics {
    position: absolute;
    top: 14px;
    left: 14px;
    display: flex;
    gap: 6px;
    z-index: 2;
  }

  .creator-card__metric {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    min-height: 26px;
    padding: 3px 9px 3px 5px;
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 999px;
    color: var(--civ-ink, #ecf4fb);
    background: rgba(11, 16, 24, 0.7);
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3);
    backdrop-filter: blur(8px);
    font-size: 11px;
    font-weight: 700;
  }

  .creator-card__metric-icon {
    display: grid;
    width: 18px;
    height: 18px;
    place-items: center;
    border-radius: 50%;
    color: var(--civ-accent, #67e8c6);
    background: rgba(103, 232, 198, 0.18);
  }

  .creator-card__metric-icon svg {
    width: 11px;
    height: 11px;
  }

  .creator-card__badge {
    position: absolute;
    top: 14px;
    right: 14px;
    z-index: 2;
    width: 58px;
    height: 58px;
    object-fit: contain;
    filter: drop-shadow(0 6px 12px rgba(0, 0, 0, 0.5));
  }

  .creator-card__profile {
    position: absolute;
    inset: 94px 0 auto;
    z-index: 3;
    display: flex;
    height: 54px;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 8px 16px;
    background: rgba(19, 28, 41, 0.75);
    backdrop-filter: blur(12px);
    border-top: 1px solid rgba(255, 255, 255, 0.08);
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
    top: -14px;
    left: 16px;
    width: 60px;
    height: 60px;
  }

  .creator-card__avatar {
    display: grid;
    width: 60px;
    height: 60px;
    place-items: center;
    border: 3px solid var(--civ-panel, #131c29);
    border-radius: 50%;
    object-fit: cover;
    color: white;
    background: var(--civ-panel-raised, #1a2636);
    font-size: 20px;
    font-weight: 700;
    box-shadow: 0 4px 14px rgba(0,0,0,0.4);
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
    color: var(--civ-ink, #ecf4fb);
    font-size: 15px;
    font-weight: 750;
    line-height: 20px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .creator-card__joined {
    color: var(--civ-muted, #a0b2c6);
    font-size: 11px;
    line-height: 15px;
  }

  .creator-card__profile-link {
    display: inline-flex;
    height: 32px;
    width: 32px;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    border: 1px solid rgba(255, 201, 130, 0.4);
    border-radius: 8px;
    color: var(--civ-warm, #ffc982);
    background: rgba(255, 201, 130, 0.12);
    text-decoration: none;
    transition: background-color 150ms ease, border-color 150ms ease, transform 150ms ease;
  }

  .creator-card__profile-link:hover {
    border-color: var(--civ-warm, #ffc982);
    background: rgba(255, 201, 130, 0.25);
    color: #fff;
    transform: scale(1.05);
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
    height: 45px;
    align-items: center;
    padding: 6px 16px;
    border-top: 1px solid var(--civ-border, rgba(42, 58, 78, 0.6));
    background: rgba(19, 28, 41, 0.6);
    backdrop-filter: blur(10px);
  }

  .creator-card__footer a {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    color: var(--civ-muted, #a0b2c6);
    font-size: 12px;
    font-weight: 650;
    text-decoration: none;
    transition: color 150ms ease;
  }

  .creator-card__footer a:hover {
    color: var(--civ-warm, #ffc982);
  }

  .creator-card__footer svg {
    width: 18px;
    height: 18px;
  }
</style>
