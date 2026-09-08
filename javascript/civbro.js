/* global gradioApp, onUiLoaded, onAfterUiUpdate */

// Some gradio rebuilds clone the tab's HTML block wholesale. The clone loses
// the iframe's id but keeps the copied src attribute, so the browser boots a
// second CivBro app right below the first (duplicate header + result grid).
// Keep the original — it owns the session state — and drop any sibling copy.
function pruneDuplicateCivBroFrames(primary) {
    const clones = [...gradioApp().querySelectorAll("iframe")]
        .filter((f) => f !== primary && (f.getAttribute("src") || "").includes("/civbro/"));
    for (const clone of clones) {
        (clone.closest(".block") ?? clone).remove();
    }
}

function initializeCivBroFrame() {
    const frame = gradioApp().querySelector("#civbro-iframe");
    if (!frame) return;
    pruneDuplicateCivBroFrames(frame);
    if (frame.getAttribute("src")) return;
    // Preserve reverse-proxy prefixes even when the host URL lacks a final '/'.
    const root = new URL(window.location.href);
    root.search = "";
    root.hash = "";
    root.pathname = root.pathname.replace(/\/?$/, "/") + "civbro/";
    frame.src = root.href;
}

onUiLoaded(initializeCivBroFrame);
onAfterUiUpdate(initializeCivBroFrame);
