// Global concurrency limiter for grid video playback.
//
// Grid video previews show their first frame immediately (preload="metadata")
// and only start *playing* when granted a slot here, so a screenful of clips
// doesn't all buffer/decode at once and stall the still-image thumbnails.
// Each caller awaits a slot, then calls the returned release() when it stops.

const MAX_CONCURRENT = 3;

let active = 0;
const waiters: Array<() => void> = [];

export function acquirePlaySlot(): Promise<() => void> {
  return new Promise<() => void>((resolve) => {
    const grant = () => {
      active++;
      let released = false;
      resolve(() => {
        if (released) return;
        released = true;
        active--;
        const next = waiters.shift();
        if (next) next();
      });
    };
    if (active < MAX_CONCURRENT) grant();
    else waiters.push(grant);
  });
}
