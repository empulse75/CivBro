export function lazyVideo(node: HTMLVideoElement, src: string) {
  let loaded = false;
  const io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          if (!loaded && src) {
            node.src = src;
            loaded = true;
          }
          node.play?.().catch(() => {});
        } else {
          node.pause?.();
        }
      }
    },
    { rootMargin: "150px" },
  );
  io.observe(node);
  return {
    destroy() {
      io.disconnect();
    },
  };
}

export function hscroll(node: HTMLElement) {
  const onWheel = (e: WheelEvent) => {
    if (e.deltaY !== 0 && node.scrollWidth > node.clientWidth) {
      e.preventDefault();
      node.scrollLeft += e.deltaY;
    }
  };
  node.addEventListener("wheel", onWheel, { passive: false });
  return {
    destroy() {
      node.removeEventListener("wheel", onWheel);
    },
  };
}
