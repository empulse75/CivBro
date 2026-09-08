import { afterEach, describe, expect, it, vi } from "vitest";
import { hscroll, lazyVideo } from "@lib/actions";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("lazyVideo", () => {
  it("loads once, controls playback, and disconnects on destroy", () => {
    let notify: IntersectionObserverCallback | undefined;
    const observe = vi.fn();
    const disconnect = vi.fn();
    const observer = vi.fn(function (callback: IntersectionObserverCallback) {
      notify = callback;
      return { observe, disconnect };
    });
    vi.stubGlobal("IntersectionObserver", observer);

    const play = vi.fn(() => Promise.resolve());
    const pause = vi.fn();
    const node = { src: "", play, pause } as unknown as HTMLVideoElement;
    const action = lazyVideo(node, "video.mp4");

    expect(observer).toHaveBeenCalledWith(expect.any(Function), { rootMargin: "150px" });
    expect(observe).toHaveBeenCalledWith(node);

    notify?.([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver);
    notify?.([{ isIntersecting: false } as IntersectionObserverEntry], {} as IntersectionObserver);
    notify?.([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver);

    expect(node.src).toBe("video.mp4");
    expect(play).toHaveBeenCalledTimes(2);
    expect(pause).toHaveBeenCalledOnce();

    action.destroy();
    expect(disconnect).toHaveBeenCalledOnce();
  });

  it("does not assign an empty source", () => {
    let notify: IntersectionObserverCallback | undefined;
    vi.stubGlobal(
      "IntersectionObserver",
      vi.fn(function (callback: IntersectionObserverCallback) {
        notify = callback;
        return { observe: vi.fn(), disconnect: vi.fn() };
      }),
    );
    const node = {
      src: "existing.mp4",
      play: vi.fn(() => Promise.resolve()),
      pause: vi.fn(),
    } as unknown as HTMLVideoElement;

    lazyVideo(node, "");
    notify?.([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver);

    expect(node.src).toBe("existing.mp4");
  });
});

describe("hscroll", () => {
  it("turns vertical wheel movement into horizontal scrolling", () => {
    let wheel: ((event: WheelEvent) => void) | undefined;
    const addEventListener = vi.fn((_type: string, listener: EventListenerOrEventListenerObject) => {
      wheel = listener as (event: WheelEvent) => void;
    });
    const removeEventListener = vi.fn();
    const node = {
      scrollWidth: 500,
      clientWidth: 200,
      scrollLeft: 25,
      addEventListener,
      removeEventListener,
    } as unknown as HTMLElement;
    const action = hscroll(node);
    const preventDefault = vi.fn();

    wheel?.({ deltaY: 40, preventDefault } as unknown as WheelEvent);

    expect(preventDefault).toHaveBeenCalledOnce();
    expect(node.scrollLeft).toBe(65);
    expect(addEventListener).toHaveBeenCalledWith("wheel", expect.any(Function), { passive: false });

    action.destroy();
    expect(removeEventListener).toHaveBeenCalledWith("wheel", wheel);
  });

  it.each([
    { deltaY: 0, scrollWidth: 500, clientWidth: 200 },
    { deltaY: 40, scrollWidth: 200, clientWidth: 200 },
  ])("ignores wheel movement when horizontal scrolling is unavailable", ({ deltaY, scrollWidth, clientWidth }) => {
    let wheel: ((event: WheelEvent) => void) | undefined;
    const node = {
      scrollWidth,
      clientWidth,
      scrollLeft: 25,
      addEventListener: vi.fn((_type: string, listener: EventListenerOrEventListenerObject) => {
        wheel = listener as (event: WheelEvent) => void;
      }),
      removeEventListener: vi.fn(),
    } as unknown as HTMLElement;
    const preventDefault = vi.fn();

    hscroll(node);
    wheel?.({ deltaY, preventDefault } as unknown as WheelEvent);

    expect(preventDefault).not.toHaveBeenCalled();
    expect(node.scrollLeft).toBe(25);
  });
});
