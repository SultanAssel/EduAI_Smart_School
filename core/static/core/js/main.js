/**
 * EduAI — Main JavaScript (v4)
 * V4 Design: scroll reveal, counters, theme, nav, card tilt, utilities
 */

/* ===== CSRF Token ===== */
function getCookie(name) {
    // Prefer meta tag (reliable, no cookie parsing)
    if (name === 'csrftoken') {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content) return meta.content;
    }
    // Fallback: parse cookies
    let v = null;
    if (document.cookie && document.cookie !== '') {
        for (const c of document.cookie.split(';')) {
            const t = c.trim();
            if (t.substring(0, name.length + 1) === (name + '=')) {
                v = decodeURIComponent(t.substring(name.length + 1));
                break;
            }
        }
    }
    return v;
}

/* ===== Theme ===== */
(function initTheme() {
    const saved = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = saved || (prefersDark ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', theme);
    requestAnimationFrame(() => {
        const icon = document.querySelector('#themeToggle i');
        if (icon) icon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
    });
})();

function toggleTheme() {
    const cur = document.documentElement.getAttribute('data-theme');
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    const icon = document.querySelector('#themeToggle i');
    if (icon) icon.className = next === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
    fetch('/api/theme/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify({ theme: next })
    }).catch(() => {});
}

/* ===== DOMContentLoaded ===== */
document.addEventListener('DOMContentLoaded', () => {

    // Theme toggle
    const themeBtn = document.getElementById('themeToggle');
    if (themeBtn) themeBtn.addEventListener('click', toggleTheme);

    // Mobile menu
    const mobileBtn = document.querySelector('.mobile-toggle');
    const navCenter = document.querySelector('.nav-center');
    if (mobileBtn && navCenter) {
        mobileBtn.addEventListener('click', () => {
            navCenter.classList.toggle('mobile-open');
            const i = mobileBtn.querySelector('i');
            if (i) i.className = navCenter.classList.contains('mobile-open') ? 'fas fa-times' : 'fas fa-bars';
        });
    }

    // Close mobile menu on outside click
    document.addEventListener('click', (e) => {
        if (navCenter && navCenter.classList.contains('mobile-open') && !e.target.closest('.nav-center') && !e.target.closest('.mobile-toggle')) {
            navCenter.classList.remove('mobile-open');
        }
    });

    // === Zen Mode Helper ===
    const _root = document.documentElement;
    const isZen = () => _root.hasAttribute('data-zen');

    window._applyZenInstant = function() {
        // Show all reveal targets immediately, no animation
        document.querySelectorAll('.reveal, .reveal-left, .reveal-right, .feat-card, .stat-chip, .card, .card-elevated, .card-interactive, .ben-card, .ben-card-v2, .pricing-card, .testi-card, .demo-card, .mod-row, .ben-group, .ctl-item').forEach(el => {
            el.classList.add('visible');
            el.classList.add('ctl-visible');
            el.style.transitionDelay = '0s';
        });
        // Remove card tilt transforms
        document.querySelectorAll('.feat-card, .pricing-card, .stat-chip, .ben-card, .testi-card').forEach(c => {
            c.style.transform = '';
        });
        // Show demo items immediately
        document.querySelectorAll('.demo-msg-user, .demo-msg-bot').forEach(el => el.classList.add('demo-animated'));
        document.querySelectorAll('.demo-reveal-item').forEach(el => el.classList.add('demo-animated'));
        document.querySelectorAll('.demo-typed-text').forEach(el => el.classList.add('demo-typing-active'));
        // Kill hero entrance delays
        document.querySelectorAll('.page-hero-icon, .page-hero h1, .page-hero p').forEach(el => {
            el.style.animationDelay = '0s';
            el.style.animation = 'none';
        });
        // Kill parallax orb transforms
        document.querySelectorAll('.hero-orb').forEach(orb => { orb.style.transform = ''; });
    }

    // === Scroll Reveal (IntersectionObserver) ===
    const revealObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                revealObserver.unobserve(entry.target);
            }
        });
    }, { threshold: 0.08, rootMargin: '0px 0px -30px 0px' });

    // === Staggered reveal for grids (BEFORE observer!) ===
    if (!isZen()) {
        document.querySelectorAll('.feat-grid, .pricing-grid, .stats-grid, .ben-grid, .testi-grid, .demo-grid, .demo-grid-secondary, .action-grid, .about-modules, .contact-grid, .ben-groups, .ben-group-cards, .mod-rows').forEach(grid => {
            Array.from(grid.children).forEach((child, i) => {
                child.style.transitionDelay = (i * 0.1) + 's';
            });
        });
    }

    // Now observe all reveal targets
    const revealTargets = document.querySelectorAll('.reveal, .reveal-left, .reveal-right, .feat-card, .stat-chip, .card, .card-elevated, .card-interactive, .ben-card, .ben-card-v2, .pricing-card, .testi-card, .demo-card, .mod-row, .ben-group');
    if (isZen()) {
        window._applyZenInstant();
    } else {
        revealTargets.forEach(el => {
            revealObserver.observe(el);
        });
    }

    // === Counter animation for stat numbers ===
    const counterObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                animateCounter(entry.target);
                counterObserver.unobserve(entry.target);
            }
        });
    }, { threshold: 0.5 });

    document.querySelectorAll('.stat-num[data-count], .hero-stat-num[data-count]').forEach(el => counterObserver.observe(el));

    function animateCounter(el) {
        if (el._counted) return;
        el._counted = true;
        const target = parseInt(el.dataset.count) || 0;
        const text = el.textContent.trim();
        const suffix = text.replace(/^\d+/, '');
        if (target <= 0) return;
        let current = 0;
        const step = Math.max(1, Math.ceil(target / 45));
        let last = 0;
        function tick(now) {
            if (now - last < 25) { requestAnimationFrame(tick); return; }
            last = now;
            current += step;
            if (current >= target) current = target;
            el.textContent = current + suffix;
            if (current < target) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
    }

    // Smooth scroll for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(a => {
        a.addEventListener('click', e => {
            const href = a.getAttribute('href');
            if (href === '#') return;
            const t = document.querySelector(href);
            if (t) { e.preventDefault(); t.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
        });
    });

    // Textarea auto-resize
    document.querySelectorAll('textarea').forEach(ta => {
        ta.addEventListener('input', () => {
            ta.style.height = 'auto';
            ta.style.height = Math.min(ta.scrollHeight, 500) + 'px';
        });
    });

    // Auto-hide alerts after 5s
    document.querySelectorAll('.result-box.ok, .result-box.err').forEach(box => {
        if (box.closest('.tab-content, .ws-body')) return;
        setTimeout(() => {
            box.style.opacity = '0';
            box.style.transform = 'translateY(-10px)';
            setTimeout(() => box.remove(), 300);
        }, 5000);
    });

    // Navbar scroll effect
    const navbar = document.querySelector('.navbar');
    window.addEventListener('scroll', () => {
        if (navbar) {
            navbar.classList.toggle('scrolled', window.scrollY > 50);
        }
    }, { passive: true });

    // === Parallax hero orbs on scroll ===
    const orbs = document.querySelectorAll('.hero-orb');
    if (orbs.length && !isZen()) {
        window.addEventListener('scroll', () => {
            if (isZen()) return;
            const y = window.scrollY;
            orbs.forEach((orb, i) => {
                const speed = 0.15 + i * 0.08;
                orb.style.transform = `translateY(${y * speed}px)`;
            });
        }, { passive: true });
    }

    // === Demo Section Animations (scroll-triggered) ===
    const demoObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (!entry.isIntersecting) return;
            const card = entry.target;
            const type = card.dataset.demo;
            demoObserver.unobserve(card);

            if (isZen()) {
                // Instantly show everything, no typing effect
                card.querySelectorAll('.demo-msg-user, .demo-msg-bot').forEach(el => el.classList.add('demo-animated'));
                card.querySelectorAll('.demo-reveal-item').forEach(el => el.classList.add('demo-animated'));
                var typedText = card.querySelector('.demo-typed-text');
                if (typedText) typedText.classList.add('demo-typing-active');
                return;
            }

            if (type === 'copilot') {
                animateCopilotChat(card);
            } else if (type === 'test-gen') {
                animateTestGen(card);
            }
        });
    }, { threshold: 0.3 });

    document.querySelectorAll('[data-demo]').forEach(el => demoObserver.observe(el));

    function animateCopilotChat(container) {
        const userMsg = container.querySelector('.demo-msg-user');
        const botMsg = container.querySelector('.demo-msg-bot');
        const typedText = container.querySelector('.demo-typed-text');
        const cursor = container.querySelector('.demo-typing');
        if (!userMsg || !botMsg || !typedText) return;

        const fullText = typedText.textContent;
        typedText.textContent = '';
        typedText.classList.add('demo-typing-active');

        // Show user message first
        setTimeout(() => {
            userMsg.classList.add('demo-animated');
        }, 200);

        // Show bot bubble after user msg
        setTimeout(() => {
            botMsg.classList.add('demo-animated');
        }, 800);

        // Start typing effect
        let charIndex = 0;
        setTimeout(() => {
            const typeInterval = setInterval(() => {
                if (charIndex < fullText.length) {
                    typedText.textContent += fullText[charIndex];
                    charIndex++;
                } else {
                    clearInterval(typeInterval);
                    if (cursor) cursor.style.display = 'none';
                }
            }, 25);
        }, 1100);
    }

    function animateTestGen(container) {
        const items = container.querySelectorAll('.demo-reveal-item');
        items.forEach((item, i) => {
            setTimeout(() => {
                item.classList.add('demo-animated');
            }, 300 + i * 400);
        });
    }

    // === Role Tab Switcher (Center Timeline) ===
    const roleTabs = document.querySelectorAll('.role-tab');
    const timelines = document.querySelectorAll('.center-tl');
    roleTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const role = tab.dataset.role;
            roleTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            timelines.forEach(tl => {
                tl.classList.remove('active');
                if (tl.dataset.tl === role) {
                    tl.classList.add('active');
                    // Re-trigger scroll animations for newly shown items
                    tl.querySelectorAll('.ctl-item').forEach(item => {
                        item.classList.remove('ctl-visible');
                    });
                    setTimeout(() => {
                        tl.querySelectorAll('.ctl-item').forEach(item => {
                            ctlObserver.observe(item);
                        });
                    }, 50);
                }
            });
        });
    });

    // === Center Timeline Scroll Animation ===
    const ctlObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('ctl-visible');
                ctlObserver.unobserve(entry.target);
            }
        });
    }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });

    document.querySelectorAll('.center-tl.active .ctl-item').forEach((item, i) => {
        if (isZen()) {
            item.classList.add('ctl-visible');
            item.style.transitionDelay = '0s';
        } else {
            item.style.transitionDelay = (i * 0.15) + 's';
            ctlObserver.observe(item);
        }
    });

    // === Card tilt on hover ===
    document.querySelectorAll('.feat-card, .pricing-card, .stat-chip, .ben-card, .testi-card').forEach(card => {
        let tiltRAF = null;
        card.addEventListener('mousemove', e => {
            if (isZen()) return;
            if (tiltRAF) cancelAnimationFrame(tiltRAF);
            tiltRAF = requestAnimationFrame(() => {
                const rect = card.getBoundingClientRect();
                const x = (e.clientX - rect.left) / rect.width;
                const y = (e.clientY - rect.top) / rect.height;
                // Dead zone: ignore outer 12% to prevent edge jitter
                if (x < 0.12 || x > 0.88 || y < 0.12 || y > 0.88) return;
                const rx = (y - 0.5) * -6;
                const ry = (x - 0.5) * 6;
                card.style.transition = 'transform .15s ease-out';
                card.style.transform = `perspective(600px) rotateX(${rx}deg) rotateY(${ry}deg)`;
            });
        });
        card.addEventListener('mouseleave', () => {
            if (tiltRAF) cancelAnimationFrame(tiltRAF);
            card.style.transition = 'transform .35s ease';
            card.style.transform = '';
        });
    });

    // === Page hero entrance ===
    document.querySelectorAll('.page-hero-icon, .page-hero h1, .page-hero p').forEach((el, i) => {
        if (isZen()) {
            el.style.animationDelay = '0s';
            el.style.animation = 'none';
        } else {
            el.style.animationDelay = (0.1 + i * 0.1) + 's';
        }
    });

    // === Footer Subscribe ===
    const subBtn = document.querySelector('.footer-top .btn');
    const subInput = document.querySelector('.footer-cta-input');
    if (subBtn && subInput) {
        subBtn.addEventListener('click', () => {
            const email = subInput.value.trim();
            if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
                showNotification((window._i18n||{}).email_invalid||'Enter a valid email', 'warning');
                return;
            }
            subBtn.disabled = true;
            subBtn.textContent = (window._i18n||{}).subscribed||'Subscribed!';
            subInput.value = '';
            showNotification((window._i18n||{}).subscribe_success||'Successfully subscribed!', 'success');
            setTimeout(() => { subBtn.disabled = false; subBtn.textContent = (window._i18n||{}).subscribe_btn||'Subscribe'; }, 4000);
        });
    }

    // === Language dropdown (navbar) ===
    document.querySelectorAll('.lang-option').forEach(opt => {
        opt.addEventListener('click', e => {
            e.preventDefault();
            const lang = opt.dataset.lang;
            const flags = { ru: 'RU', kk: 'KZ', en: 'EN' };
            fetch('/api/language/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({ language: lang })
            }).then(r => {
                if (r.ok) {
                    const el = document.getElementById('currentLangFlag');
                    if (el) el.textContent = flags[lang] || lang.toUpperCase();
                    showNotification((window._i18n||{}).lang_changed||'Language changed!', 'success');
                    setTimeout(() => location.reload(), 800);
                }
            }).catch(() => {});
        });
    });
});

/* ===== Notification Helper ===== */
function showNotification(message, type = 'info') {
    const colors = { success: 'var(--c1)', error: 'var(--err)', info: 'var(--c2)', warning: 'var(--c3)' };
    const n = document.createElement('div');
    n.style.cssText = `
        position:fixed;top:76px;right:20px;padding:.75rem 1.1rem;
        border-radius:var(--r-sm);background:var(--card);border:1px solid var(--border);
        border-left:4px solid ${colors[type] || colors.info};
        box-shadow:var(--sh-lg);z-index:10000;max-width:380px;font-size:.88rem;
        animation:fadeUp .3s ease;transition:all .3s ease;display:flex;align-items:flex-start;gap:.5rem;
    `;
    const txt = document.createElement('span');
    txt.style.flex = '1';
    txt.textContent = message;
    n.appendChild(txt);

    function dismiss() {
        n.style.opacity = '0';
        n.style.transform = 'translateX(20px)';
        setTimeout(() => n.remove(), 300);
    }

    if (type === 'error' || type === 'warning') {
        // Errors/warnings: stay until manually closed
        const btn = document.createElement('span');
        btn.textContent = '✕';
        btn.style.cssText = 'cursor:pointer;font-weight:700;color:var(--t3);font-size:.9rem;line-height:1;flex-shrink:0;';
        btn.addEventListener('click', dismiss);
        n.appendChild(btn);
    } else {
        // Success/info: auto-dismiss after 4s
        setTimeout(dismiss, 4000);
    }
    document.body.appendChild(n);
}

/* ===== Utilities ===== */
function _esc(s) {
    var d = document.createElement('div'); d.textContent = s; return d.innerHTML;
}

function formatNumber(num) {
    if (num >= 1e6) return (num / 1e6).toFixed(1) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(1) + 'K';
    return num.toString();
}

function debounce(fn, ms) {
    let t;
    return function (...args) { clearTimeout(t); t = setTimeout(() => fn.apply(this, args), ms); };
}

async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showNotification((window._i18n||{}).copied||'Copied!', 'success');
    } catch {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        showNotification((window._i18n||{}).copied||'Copied!', 'success');
    }
}

/* ═══════════════════════════════════════════════════
   Accessibility FAB — Floating toolbar logic (draggable)
   ═══════════════════════════════════════════════════ */
(function initA11yFab(){
    var fab = document.getElementById('a11yFab');
    if(!fab) return;
    var btn = document.getElementById('a11yFabBtn');
    var panel = document.getElementById('a11yPanel');
    var root = document.documentElement;

    /* ── Draggable FAB ── */
    var isDragging = false, hasMoved = false;
    var startX, startY, fabStartX, fabStartY;
    var DRAG_THRESHOLD = 5; // px before we consider it a drag

    function getFabPos() {
        var r = fab.getBoundingClientRect();
        return { x: r.left, y: r.top };
    }

    function setFabPos(x, y) {
        // Clamp to viewport
        var bw = btn.offsetWidth, bh = btn.offsetHeight;
        x = Math.max(0, Math.min(window.innerWidth - bw, x));
        y = Math.max(0, Math.min(window.innerHeight - bh, y));
        fab.style.left = x + 'px';
        fab.style.top = y + 'px';
        fab.style.right = 'auto';
        fab.style.bottom = 'auto';
        localStorage.setItem('eduai_fab_pos', JSON.stringify({x: x, y: y}));
    }

    function positionPanel() {
        if (!panel.classList.contains('open')) return;
        var fr = fab.getBoundingClientRect();
        var pw = 300, ph = Math.min(panel.scrollHeight, window.innerHeight * 0.6);
        // Default: above the FAB, aligned right
        var px = fr.right - pw;
        var py = fr.top - ph - 8;
        // If not enough space above, show below
        if (py < 8) py = fr.bottom + 8;
        // If not enough space to the left, align left
        if (px < 8) px = 8;
        // If off right edge
        if (px + pw > window.innerWidth - 8) px = window.innerWidth - pw - 8;
        // Clamp bottom
        if (py + ph > window.innerHeight - 8) py = window.innerHeight - ph - 8;
        panel.style.left = px + 'px';
        panel.style.top = py + 'px';
        panel.style.right = 'auto';
        panel.style.bottom = 'auto';
        panel.style.maxHeight = '60vh';
    }

    function onDragStart(ex, ey) {
        isDragging = true; hasMoved = false;
        startX = ex; startY = ey;
        var pos = getFabPos();
        fabStartX = pos.x; fabStartY = pos.y;
    }

    function onDragMove(ex, ey) {
        if (!isDragging) return;
        var dx = ex - startX, dy = ey - startY;
        if (!hasMoved && Math.abs(dx) < DRAG_THRESHOLD && Math.abs(dy) < DRAG_THRESHOLD) return;
        hasMoved = true;
        btn.classList.add('dragging');
        if (panel.classList.contains('open')) panel.classList.remove('open');
        setFabPos(fabStartX + dx, fabStartY + dy);
    }

    function onDragEnd() {
        isDragging = false;
        btn.classList.remove('dragging');
    }

    // Mouse events
    btn.addEventListener('mousedown', function(e) {
        if (e.button !== 0) return;
        e.preventDefault();
        onDragStart(e.clientX, e.clientY);
    });
    document.addEventListener('mousemove', function(e) {
        if (isDragging) { e.preventDefault(); onDragMove(e.clientX, e.clientY); }
    });
    document.addEventListener('mouseup', function() {
        if (isDragging) onDragEnd();
    });

    // Touch events
    btn.addEventListener('touchstart', function(e) {
        var t = e.touches[0];
        onDragStart(t.clientX, t.clientY);
    }, { passive: true });
    document.addEventListener('touchmove', function(e) {
        if (!isDragging) return;
        var t = e.touches[0];
        onDragMove(t.clientX, t.clientY);
        if (hasMoved) e.preventDefault();
    }, { passive: false });
    document.addEventListener('touchend', function() {
        if (isDragging) onDragEnd();
    });

    // Click = toggle panel (only if not dragged)
    btn.addEventListener('click', function(e){
        e.stopPropagation();
        if (hasMoved) { hasMoved = false; return; }
        panel.classList.toggle('open');
        positionPanel();
    });
    document.addEventListener('click', function(e){
        if(panel.classList.contains('open') && !panel.contains(e.target) && e.target !== btn){
            panel.classList.remove('open');
        }
    });
    window.addEventListener('resize', positionPanel);

    // Restore saved position
    try {
        var saved = JSON.parse(localStorage.getItem('eduai_fab_pos'));
        if (saved && typeof saved.x === 'number') {
            setFabPos(saved.x, saved.y);
        }
    } catch(e) {}

    // Save helper — persist to server
    function saveA11y(data){
        fetch('/api/accessibility/', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken')},
            body: JSON.stringify(data)
        }).catch(function(){});
    }

    // ── Font Family Pills ──
    var pills = document.querySelectorAll('#a11yFontPills .a11y-font-pill');
    pills.forEach(function(pill){
        pill.addEventListener('click', function(){
            pills.forEach(function(p){ p.classList.remove('active'); });
            pill.classList.add('active');
            var font = pill.dataset.font;
            if(font === 'default') root.removeAttribute('data-font');
            else root.setAttribute('data-font', font);
            localStorage.setItem('eduai_font', font);
            saveA11y({font_family: font});
        });
    });

    // ── Font Size Slider ──
    var sizeSlider = document.getElementById('fabFontSize');
    var sizeVal = document.getElementById('fabFontVal');
    if(sizeSlider) sizeSlider.addEventListener('input', function(){
        var v = parseInt(this.value);
        sizeVal.textContent = v + 'px';
        if(v === 16){
            root.style.fontSize = '';
            root.removeAttribute('data-font-size');
        } else {
            root.style.fontSize = v + 'px';
            root.setAttribute('data-font-size', v);
        }
        localStorage.setItem('eduai_font_size', v);
    });
    if(sizeSlider) sizeSlider.addEventListener('change', function(){
        saveA11y({font_size: parseInt(this.value)});
    });

    // ── Toggle Switches ──
    function setupToggle(id, attr, lsKey, dataKey){
        var el = document.getElementById(id);
        if(!el) return;
        el.addEventListener('change', function(){
            if(this.checked) root.setAttribute(attr, 'true');
            else root.removeAttribute(attr);
            localStorage.setItem(lsKey, this.checked ? 'true' : 'false');
            var d = {}; d[dataKey] = this.checked;
            saveA11y(d);
        });
    }
    setupToggle('fabContrast',  'data-high-contrast', 'eduai_contrast',  'high_contrast');
    setupToggle('fabEasyRead',  'data-easy-read',     'eduai_easyread',  'easy_read');
    setupToggle('fabTts',       'data-tts',           'eduai_tts',       'text_to_speech');

    // Zen toggle — also kill live animations when enabled
    var zenEl = document.getElementById('fabZen');
    if(zenEl){
        zenEl.addEventListener('change', function(){
            if(this.checked){
                root.setAttribute('data-zen', 'true');
                window._applyZenInstant();
            } else {
                root.removeAttribute('data-zen');
            }
            localStorage.setItem('eduai_zen', this.checked ? 'true' : 'false');
            saveA11y({zen_mode: this.checked});
        });
    }

    var voiceToggle = document.getElementById('fabVoice');
    if(voiceToggle) voiceToggle.addEventListener('change', function(){
        localStorage.setItem('eduai_voice_input', this.checked ? 'true' : 'false');
        saveA11y({voice_input: this.checked});
        // Show/hide voice buttons globally
        document.querySelectorAll('.voice-btn').forEach(function(b){
            b.style.display = this.checked ? '' : 'none';
        }.bind(this));
    });

    // ── Reset Button ──
    var resetBtn = document.getElementById('fabReset');
    if(resetBtn) resetBtn.addEventListener('click', function(){
        root.removeAttribute('data-font');
        root.removeAttribute('data-font-size');
        root.style.fontSize = '';
        root.removeAttribute('data-high-contrast');
        root.removeAttribute('data-easy-read');
        root.removeAttribute('data-zen');
        root.removeAttribute('data-tts');
        pills.forEach(function(p){ p.classList.remove('active'); });
        if(pills[0]) pills[0].classList.add('active');
        if(sizeSlider){ sizeSlider.value = 16; sizeVal.textContent = '16px'; }
        ['fabContrast','fabEasyRead','fabZen','fabTts','fabVoice'].forEach(function(id){
            var el = document.getElementById(id);
            if(el) el.checked = false;
        });
        ['eduai_font','eduai_font_size','eduai_contrast','eduai_easyread','eduai_zen','eduai_tts','eduai_voice_input','eduai_fab_pos'].forEach(function(k){
            localStorage.removeItem(k);
        });
        saveA11y({font_family:'default', font_size:16, high_contrast:false, easy_read:false, zen_mode:false, text_to_speech:false, voice_input:false});
        showNotification((window._i18n||{}).settings_reset||'Settings reset', 'success');
    });

    // ── Restore from localStorage on page load (instant, no FOUC) ──
    var lsFont = localStorage.getItem('eduai_font');
    if(lsFont && lsFont !== 'default') root.setAttribute('data-font', lsFont);
    var lsSize = localStorage.getItem('eduai_font_size');
    if(lsSize && lsSize !== '16'){ root.style.fontSize = lsSize + 'px'; root.setAttribute('data-font-size', lsSize); if(sizeSlider){ sizeSlider.value = lsSize; sizeVal.textContent = lsSize + 'px'; } }

    // Restore all toggles from localStorage
    function restoreToggle(lsKey, attr, checkboxId){
        var v = localStorage.getItem(lsKey);
        if(v === 'true'){ root.setAttribute(attr, 'true'); var cb = document.getElementById(checkboxId); if(cb) cb.checked = true; }
    }
    restoreToggle('eduai_zen',      'data-zen',           'fabZen');
    restoreToggle('eduai_contrast', 'data-high-contrast', 'fabContrast');
    restoreToggle('eduai_easyread', 'data-easy-read',     'fabEasyRead');
    restoreToggle('eduai_tts',      'data-tts',           'fabTts');

    // Restore font pill highlight
    if(lsFont){
        pills.forEach(function(p){ p.classList.toggle('active', p.dataset.font === lsFont); });
    }

    // Restore voice toggle (doesn't set data-attr, just checkbox)
    var lsVoice = localStorage.getItem('eduai_voice_input');
    if(lsVoice === 'true'){
        var vc = document.getElementById('fabVoice');
        if(vc) vc.checked = true;
    }
})();

/* ═══════════════════════════════════════════════════
   Voice Input — Web Speech API + MediaRecorder fallback
   Works in ALL browsers: Chrome, Firefox, Edge, Safari
   Usage: EduAI.voiceInput.toggle(targetElement, opts)
   ═══════════════════════════════════════════════════ */
window.EduAI = window.EduAI || {};
EduAI.voiceInput = (function(){
    var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    var hasNativeSTT = !!SpeechRecognition;
    var hasMediaRecorder = !!(navigator.mediaDevices && window.MediaRecorder);
    var activeRecognition = null;
    var activeRecorder = null;

    /* ── Native Web Speech API (Chrome, Edge) ── */
    function startNative(targetEl, opts){
        opts = opts || {};
        if(activeRecognition){ activeRecognition.abort(); activeRecognition = null; }

        var recognition = new SpeechRecognition();
        recognition.continuous = opts.continuous || false;
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;
        var lang = document.documentElement.lang || 'ru';
        var langMap = {'ru':'ru-RU','kk':'kk-KZ','en':'en-US'};
        recognition.lang = langMap[lang] || lang + '-' + lang.toUpperCase();

        var finalText = '';
        var btn = opts.button;

        recognition.onstart = function(){
            activeRecognition = recognition;
            if(btn) btn.classList.add('recording');
            if(opts.onStart) opts.onStart();
        };
        recognition.onresult = function(e){
            var interim = '';
            for(var i = e.resultIndex; i < e.results.length; i++){
                var transcript = e.results[i][0].transcript;
                if(e.results[i].isFinal) finalText += transcript + ' ';
                else interim = transcript;
            }
            if(targetEl){
                var marker = targetEl._voiceOrigin || '';
                targetEl.value = marker + finalText + interim;
                targetEl.dispatchEvent(new Event('input', {bubbles:true}));
            }
            if(opts.onResult) opts.onResult(finalText + interim);
        };
        recognition.onend = function(){
            activeRecognition = null;
            if(btn) btn.classList.remove('recording');
            if(opts.onEnd) opts.onEnd(finalText.trim());
        };
        recognition.onerror = function(e){
            activeRecognition = null;
            if(btn) btn.classList.remove('recording');
            if(e.error !== 'aborted' && e.error !== 'no-speech'){
                console.warn('Voice input error:', e.error);
            }
        };

        if(targetEl) targetEl._voiceOrigin = targetEl.value || '';
        finalText = '';
        recognition.start();
        return recognition;
    }

    function stopNative(){
        if(activeRecognition){ activeRecognition.stop(); activeRecognition = null; }
    }

    /* ── MediaRecorder fallback (Firefox, Safari) ── */
    function startRecorder(targetEl, opts){
        opts = opts || {};
        if(activeRecorder){ stopRecorder(); return; }

        var btn = opts.button;
        navigator.mediaDevices.getUserMedia({audio: true}).then(function(stream){
            var chunks = [];
            var mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus'
                         : MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm'
                         : MediaRecorder.isTypeSupported('audio/ogg;codecs=opus') ? 'audio/ogg;codecs=opus'
                         : '';
            var recOpts = mimeType ? {mimeType: mimeType} : {};
            var recorder = new MediaRecorder(stream, recOpts);
            activeRecorder = recorder;

            recorder.ondataavailable = function(e){ if(e.data.size > 0) chunks.push(e.data); };
            recorder.onstart = function(){
                if(btn) btn.classList.add('recording');
                if(opts.onStart) opts.onStart();
            };
            recorder.onstop = function(){
                activeRecorder = null;
                stream.getTracks().forEach(function(t){ t.stop(); });
                if(btn){ btn.classList.remove('recording'); btn.classList.add('processing'); }

                var blob = new Blob(chunks, {type: mimeType || 'audio/webm'});
                var formData = new FormData();
                formData.append('audio', blob, 'recording.webm');
                formData.append('language', document.documentElement.lang || 'ru');

                fetch('/api/speech-to-text/', {
                    method: 'POST',
                    headers: {'X-CSRFToken': getCookie('csrftoken')},
                    body: formData
                }).then(function(r){ return r.json(); })
                .then(function(data){
                    if(btn) btn.classList.remove('processing');
                    if(data.text){
                        if(targetEl){
                            var origin = targetEl._voiceOrigin || targetEl.value || '';
                            targetEl.value = origin + (origin ? ' ' : '') + data.text;
                            targetEl.dispatchEvent(new Event('input', {bubbles:true}));
                        }
                        if(opts.onEnd) opts.onEnd(data.text);
                        if(opts.onResult) opts.onResult(data.text);
                    } else {
                        if(data.error === 'no_speech') showNotification((window._i18n||{}).stt_no_speech||'No speech detected. Try again.', 'warning');
                        else showNotification((window._i18n||{}).stt_fail||'Could not recognize speech', 'warning');
                        if(opts.onEnd) opts.onEnd('');
                    }
                }).catch(function(){
                    if(btn) btn.classList.remove('processing');
                    showNotification((window._i18n||{}).stt_error||'Speech recognition error', 'error');
                    if(opts.onEnd) opts.onEnd('');
                });
            };

            if(targetEl) targetEl._voiceOrigin = targetEl.value || '';
            recorder.start();
        }).catch(function(err){
            showNotification((window._i18n||{}).mic_denied||'No microphone access. Allow in browser settings.', 'warning');
        });
    }

    function stopRecorder(){
        if(activeRecorder && activeRecorder.state === 'recording'){
            activeRecorder.stop();
        }
    }

    /* ── Public API ── */
    if(!hasNativeSTT && !hasMediaRecorder){
        return {
            supported: false,
            start: function(){ showNotification((window._i18n||{}).stt_unsupported||'Voice input is not supported in this browser.', 'warning'); },
            stop: function(){},
            toggle: function(){ showNotification((window._i18n||{}).stt_unsupported||'Voice input is not supported in this browser.', 'warning'); }
        };
    }

    return {
        supported: true,
        start: function(targetEl, opts){
            if(hasNativeSTT) startNative(targetEl, opts);
            else startRecorder(targetEl, opts);
        },
        stop: function(){
            if(hasNativeSTT) stopNative();
            else stopRecorder();
        },
        toggle: function(targetEl, opts){
            if(hasNativeSTT){
                if(activeRecognition){ stopNative(); return; }
                startNative(targetEl, opts);
            } else {
                if(activeRecorder && activeRecorder.state === 'recording'){ stopRecorder(); return; }
                startRecorder(targetEl, opts);
            }
        }
    };
})();

/* ═══════════════════════════════════════════════════
   Quick TTS — Browser native fallback for fast playback
   Falls back to edge-tts server for quality
   ═══════════════════════════════════════════════════ */
EduAI.quickTTS = (function(){
    var synth = window.speechSynthesis;

    function speakBrowser(text, opts){
        opts = opts || {};
        if(!synth) return false;
        synth.cancel();
        var utt = new SpeechSynthesisUtterance(text.substring(0, 500));
        var lang = document.documentElement.lang || 'ru';
        var langMap = {'ru':'ru-RU','kk':'kk-KZ','en':'en-US'};
        utt.lang = langMap[lang] || 'ru-RU';
        utt.rate = 1 + (opts.speed || 0) / 100;
        // Volume: accept 0-1 float or 0-100 int
        var vol = opts.volume != null ? opts.volume : 1;
        utt.volume = vol > 1 ? vol / 100 : vol;
        utt.onend = opts.onEnd || function(){};
        utt.onerror = opts.onEnd || function(){};
        synth.speak(utt);
        return true;
    }

    function stop(){
        if(synth) synth.cancel();
    }

    return {speak: speakBrowser, stop: stop, supported: !!synth};
})();
