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
    let cls = "civ-download-btn relative w-9 h-9 rounded-full bg-black/60 backdrop-blur-md border text-white flex items-center justify-center transition-all duration-200 cursor-pointer shadow-md hover:scale-105 active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--civ-accent,#67e8c6)] ";
    if (spinner) return cls + "bg-[#e03131]/40 border-[#e03131] hover:bg-[#e03131] hover:border-[#e03131] text-white shadow-[0_0_12px_rgba(224,49,49,0.5)]";
    if (isLocked) return cls + "border-[#fab005] text-[#fab005] bg-[#fab005]/15 hover:bg-[#fab005] hover:text-[#0b1018] hover:border-[#fab005] shadow-[0_0_12px_rgba(250,176,5,0.3)]";
    if (isApiLocked) return cls + "border-[#ef4444] text-[#ef4444] bg-[#ef4444]/15 hover:bg-[#ef4444] hover:text-white hover:border-[#ef4444]";
    if (isUnlocked) return cls + "border-[#fab005] text-[#fab005] bg-[#fab005]/15 hover:bg-[#fab005] hover:text-[#0b1018]";
    if (isDone) return cls + "border-[#22c55e] text-[#22c55e] bg-[#22c55e]/15 hover:bg-[#ef4444] hover:border-[#ef4444] hover:text-white shadow-[0_0_10px_rgba(34,197,94,0.3)]";
    return cls + "border-white/20 text-white/90 hover:bg-[var(--civ-accent,#67e8c6)] hover:border-[var(--civ-accent,#67e8c6)] hover:text-[#0b1018] hover:shadow-[0_0_14px_rgba(103,232,198,0.5)]";
  });
</script>

<button
  type="button"
  class={btnClass}
  onclick={onclick}
  aria-label={label}
  title={label}
>
  {#if spinner}
    <svg class="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
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
    <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  {:else}
    <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
      <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/>
    </svg>
  {/if}
</button>
