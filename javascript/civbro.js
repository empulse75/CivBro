/* global gradioApp, onUiLoaded, onAfterUiUpdate */
function initializeCivBroFrame() {
    const frame = gradioApp().querySelector("#civbro-iframe");
    if (!frame || frame.getAttribute("src")) return;
    // Preserve reverse-proxy prefixes even when the host URL lacks a final '/'.
    const root = new URL(window.location.href);
    root.search = "";
    root.hash = "";
    root.pathname = root.pathname.replace(/\/?$/, "/") + "civbro/";
    frame.src = root.href;
}
onUiLoaded(initializeCivBroFrame);
onAfterUiUpdate(initializeCivBroFrame);
