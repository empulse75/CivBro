window._civbroLoadingSkeleton = '<div class="civbro-loading-skeleton">' + Array(16).fill('<div class="civbro-skeleton-card"></div>').join('') + '</div>';
var _civbroScrollLocked = false;
var _civbroPage = 1;

(function() {
    var ACTIVE = {};
    var WAVE_CANVASES = {};
    var ANIM_ID = null;

    function smoothstep(edge0, edge1, x) {
        var t = Math.max(0, Math.min(1, (x - edge0) / (edge1 - edge0)));
        return t * t * (3 - 2 * t);
    }

    function drawWave(canvas, health, time) {
        var ctx = canvas.getContext('2d');
        var w = canvas.width;
        var h = canvas.height;
        if (w < 2 || h < 2) return;
        ctx.clearRect(0, 0, w, h);

        var waveSpeed = 3.0;
        var wavePeriod = 1.5;
        var waveAmplitude = 0.06;

        var waveAmpScale = Math.min(
            smoothstep(1.0, 1.0 - waveAmplitude, health),
            smoothstep(0.0, waveAmplitude * 2.0, health)
        );

        ctx.beginPath();
        ctx.moveTo(0, 0);

        var edgeX = w * health;

        var steps = h;
        for (var y = 0; y <= steps; y++) {
            var uvY = y / h;
            var sinWave = Math.sin((time + uvY / wavePeriod) * waveSpeed);
            var scaledWave = (sinWave * 0.5) + 0.5;
            var waveOffset = scaledWave * waveAmplitude * waveAmpScale * w;
            var x = edgeX + waveOffset - (waveAmplitude * waveAmpScale * w * 0.5);
            ctx.lineTo(x, y);
        }

        ctx.lineTo(0, h);
        ctx.closePath();

        var grad = ctx.createLinearGradient(0, 0, edgeX, 0);
        grad.addColorStop(0, 'rgba(34,197,94,0.15)');
        grad.addColorStop(0.6, 'rgba(34,197,94,0.32)');
        grad.addColorStop(1, 'rgba(34,197,94,0.40)');
        ctx.fillStyle = grad;
        ctx.fill();
    }

    function startWaveLoop() {
        if (ANIM_ID) return;
        var lastFrame = 0;
        function tick(ts) {
            if (ts - lastFrame < 50) {
                ANIM_ID = requestAnimationFrame(tick);
                return;
            }
            lastFrame = ts;
            var time = ts * 0.001;
            var hasAny = false;
            Object.keys(WAVE_CANVASES).forEach(function(mid) {
                var c = WAVE_CANVASES[mid];
                if (!c || !c.parentNode) {
                    delete WAVE_CANVASES[mid];
                    return;
                }
                hasAny = true;
                var pill = c.parentNode;
                var rect = pill.getBoundingClientRect();
                if (rect.width > 2 && rect.height > 2) {
                    c.width = rect.width;
                    c.height = rect.height;
                    c.style.width = rect.width + 'px';
                    c.style.height = rect.height + 'px';
                }
                var progress = (ACTIVE[mid] || 0) / 100;
                if (progress > 0) {
                    drawWave(c, progress, time);
                }
            });
            if (hasAny) {
                ANIM_ID = requestAnimationFrame(tick);
            } else {
                ANIM_ID = null;
            }
        }
        ANIM_ID = requestAnimationFrame(tick);
    }

    function fetchProgress() {
        fetch('/civitai/download_status')
            .then(function(r) { return r.ok ? r.json() : []; })
            .then(function(tasks) {
                var fresh = {};
                if (tasks && tasks.length) {
                    tasks.forEach(function(t) {
                        if (t.status === 'downloading') {
                            fresh[t.model_id] = {pct: Math.round(t.progress || 0), queued: 0};
                        } else if (t.status === 'queued') {
                            fresh[t.model_id] = {pct: 0, queued: t.queue_position || 0};
                        }
                    });
                }
                ACTIVE = fresh;
                renderProgress(fresh);
            })
            .catch(function(){});
    }

    function renderProgress(active, hasActive) {
        var cards = document.querySelectorAll('.civbro-card[data-model-id]');
        cards.forEach(function(card) {
            var modelId = card.getAttribute('data-model-id');
            var pill = card.querySelector('.civbro-info-pill');
            if (!pill) return;

            var info = active[modelId];
            if (info && info.queued > 0) {
                pill.classList.add('civbro-downloading');
                var c = pill.querySelector('.civbro-dl-canvas');
                if (c) c.remove();
                delete WAVE_CANVASES[modelId];

                var pctEl = pill.querySelector('.civbro-dl-percent');
                if (!pctEl) {
                    pctEl = document.createElement('span');
                    pctEl.className = 'civbro-dl-percent';
                    pctEl.style.color = '#fbbf24';
                    pill.appendChild(pctEl);
                }
                pctEl.textContent = ' | #' + info.queued;

                if (!pill.dataset.civbroCancelWired) {
                    pill.dataset.civbroCancelWired = '1';
                    pill.addEventListener('click', function(e) {
                        e.stopPropagation();
                        fetch('/civitai/download_cancel/' + modelId, {method: 'POST'});
                    });
                }
            } else if (info && info.queued === 0) {
                pill.classList.add('civbro-downloading');

                var canvas = pill.querySelector('.civbro-dl-canvas');
                if (!canvas) {
                    canvas = document.createElement('canvas');
                    canvas.className = 'civbro-dl-canvas';
                    pill.insertBefore(canvas, pill.firstChild);
                    startWaveLoop();
                }
                WAVE_CANVASES[modelId] = canvas;

                var pctEl = pill.querySelector('.civbro-dl-percent');
                if (!pctEl) {
                    pctEl = document.createElement('span');
                    pctEl.className = 'civbro-dl-percent';
                    pctEl.style.color = '#4ade80';
                    pill.appendChild(pctEl);
                }
                pctEl.textContent = ' | ' + info.pct + '%';

                if (!pill.dataset.civbroCancelWired) {
                    pill.dataset.civbroCancelWired = '1';
                    pill.addEventListener('click', function(e) {
                        e.stopPropagation();
                        fetch('/civitai/download_cancel/' + modelId, {method: 'POST'});
                    });
                }
            } else {
                pill.classList.remove('civbro-downloading');
                delete WAVE_CANVASES[modelId];
                var canvas = pill.querySelector('.civbro-dl-canvas');
                if (canvas) canvas.remove();
                var pctEl = pill.querySelector('.civbro-dl-percent');
                if (pctEl) pctEl.remove();
            }
        });
    }

    fetchProgress();
    setInterval(fetchProgress, 500);

    document.addEventListener('DOMContentLoaded', function() {
        setTimeout(fetchProgress, 2000);
    });
})();

document.addEventListener('scroll', function(e) {
    if (_civbroScrollLocked) return;
    var scrollTop = window.scrollY || document.documentElement.scrollTop;
    var docH = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
    if ((window.innerHeight + scrollTop) >= docH - 400) {
        _civbroScrollLocked = true;
        _civbroPage++;
        var trigger = document.querySelector('#civbro-page-trigger textarea');
        if (trigger) {
            trigger.value = String(_civbroPage);
            trigger.dispatchEvent(new Event('input', {bubbles: true}));
            trigger.dispatchEvent(new Event('change', {bubbles: true}));
        }
        setTimeout(function(){ _civbroScrollLocked = false; }, 3000);
    }
}, {capture: true, passive: true});
document.addEventListener('DOMContentLoaded', function() {
    var observer = new MutationObserver(function() {
        var sidebar = document.querySelector('#civbro-sidebar');
        if (!sidebar) return;
        sidebar.querySelectorAll('.form label, #sortType select, #timePeriod select').forEach(function(el) {
            if (el.dataset.civbroWired) return;
            el.dataset.civbroWired = '1';
            el.addEventListener('click', function() {
                _civbroPage = 1;
                var tr = document.querySelector('#civbro-page-trigger textarea');
                if (tr) { tr.value = '1'; tr.dispatchEvent(new Event('input', {bubbles: true})); }
                var gw = document.querySelector('#civbro-grid-wrapper');
                if (gw) { var p = gw.querySelector('.prose'); if (p) p.innerHTML = window._civbroLoadingSkeleton; }
                var fs = el.closest('fieldset');
                if (fs) {
                    setTimeout(function() { fs.dispatchEvent(new Event('change', {bubbles: true})); }, 100);
                }
                var btn = document.querySelector('#civbro-search-btn');
                if (btn) setTimeout(function() { btn.click(); }, 1200);
            });
        });
        var searchBox = sidebar.querySelector('#civbro-sidebar textarea');
        if (searchBox && !searchBox.dataset.civbroWired) {
            searchBox.dataset.civbroWired = '1';
            searchBox.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    _civbroPage = 1;
                    var gw = document.querySelector('#civbro-grid-wrapper');
                    if (gw) { var p = gw.querySelector('.prose'); if (p) p.innerHTML = window._civbroLoadingSkeleton; }
                    var btn = document.querySelector('#civbro-search-btn');
                    if (btn) setTimeout(function() { btn.click(); }, 100);
                }
            });
        }
    });
    observer.observe(document.body, {childList: true, subtree: true});
});

(function() {
    var _tick = 0;
    setInterval(function() {
        _tick++;
        if (_tick % 5 !== 0) return;
        var fs = document.querySelector('.civbro-local-fetch-status');
        if (!fs) return;
        var trigger = document.querySelector('#civbro_local_refresh textarea');
        if (!trigger) return;
        trigger.value = String(Date.now());
        trigger.dispatchEvent(new Event('input', {bubbles: true}));
        setTimeout(function() { trigger.dispatchEvent(new Event('change', {bubbles: true})); }, 50);
    }, 2000);
})();

(function(){
    var videoBuffer = 0.2;
    var ticking = false;
    function updateVideos() {
        var videos = document.querySelectorAll('video.civbro-card-media');
        var vh = window.innerHeight;
        for (var i = 0; i < videos.length; i++) {
            var rect = videos[i].getBoundingClientRect();
            var visible = rect.bottom > -vh * videoBuffer && rect.top < vh * (1 + videoBuffer);
            if (visible) {
                if (videos[i].paused) videos[i].play().catch(function(){});
            } else {
                if (!videos[i].paused) videos[i].pause();
            }
        }
        ticking = false;
    }
    document.addEventListener('scroll', function() {
        if (!ticking) { requestAnimationFrame(updateVideos); ticking = true; }
    }, {passive: true});
    window.addEventListener('resize', updateVideos, {passive: true});
    setTimeout(updateVideos, 1000);
})();
