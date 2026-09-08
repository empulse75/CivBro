<script lang="ts">
  interface Props {
    status: "idle" | "busy" | "active" | "completed" | "failed" | "installed" | "buzzLocked" | "buzzUnlocked" | "apikeyLocked";
    label: string;
    onclick: (e: Event) => void;
  }

  let { status, label, onclick }: Props = $props();

  const isActive = $derived(status === "active");
  const isIdle = $derived(status === "idle");
  const isDone = $derived(status === "completed" || status === "installed");
  const spinner = $derived(status === "active" || status === "busy");
  const isLocked = $derived(status === "buzzLocked");
  const isApiLocked = $derived(status === "apikeyLocked");
  const isUnlocked = $derived(status === "buzzUnlocked");

  let btnClass = $derived.by(() => {
    let cls = "w-8 h-8 rounded-full bg-black/50 backdrop-blur-sm border text-white flex items-center justify-center transition-all cursor-pointer ";
    if (spinner) return cls + "bg-[#e03131]/40 border-[#e03131] hover:bg-[#e03131] hover:border-[#e03131] hover:text-white";
    if (isLocked) return cls + "border-[#fab005] text-[#fab005] hover:bg-[#fab005] hover:text-[#1a1b1e]";
    if (isApiLocked) return cls + "border-[#dc2626] text-[#dc2626] hover:bg-[#dc2626] hover:text-white";
    if (isUnlocked) return cls + "border-[#fab005] text-[#fab005] hover:bg-[#fab005] hover:text-[#1a1b1e]";
    if (isDone) return cls + "border-[#22c55e] text-[#22c55e] hover:bg-[#dc2626] hover:border-[#dc2626] hover:text-white";
    return cls + "border-white/10 hover:bg-[#2563eb] hover:border-[#2563eb]";
  });
</script>

<div
  class={btnClass}
  onclick={onclick}
  onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.stopPropagation(); onclick(e); } }}
  role="button"
  tabindex="0"
  aria-label={label}
  title={label}
>
  {#if spinner}
    <svg class="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M21 12a9 9 0 11-6.2-8.6"/>
    </svg>
  {:else if isLocked || isApiLocked}
    <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="0">
      <rect x="5" y="11" width="14" height="10" rx="2"/>
      <path d="M8 11V7a4 4 0 018 0v4" fill="none" stroke="currentColor" stroke-width="2"/>
    </svg>
  {:else if isUnlocked}
    <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="0">
      <rect x="5" y="11" width="14" height="10" rx="2"/>
      <path d="M16 11V8a4 4 0 00-7.7-1.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      <path d="M12 15v2" fill="none" stroke="currentColor" stroke-width="2"/>
    </svg>
  {:else if isDone}
    <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  {:else}
    <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/>
    </svg>
  {/if}
</div>
