/**
 * Settings -> Supporter Key panel: Collector's Pressed Vinyl Plaque & offline Ed25519 key activation.
 *
 * Uses safe DOM creation helpers exclusively (never raw HTML markup strings).
 */

import { UnauthorizedError } from '../http.js';
import { updateCachedSupporter } from '../app-info.js';
import {
    createMiniBrandMarkSvg,
    createPlaqueVinylEmblemSvg,
    createVinylGlyphSvg,
    supportUrl,
} from '../supporter-ui.js';

const DEFAULT_SUPPORTER_DOC = Object.freeze({
    active: false,
    status: 'inactive',
    tier: null,
    issued_at: null,
    key_preview: null,
    order_preview: null,
    origin: 'none',
    env_configured: false,
    can_edit: true,
    can_clear: false,
    show_in_header: true,
});

function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
        if (value === undefined || value === null || value === false) continue;
        if (key === 'className') {
            node.className = value;
        } else if (key === 'textContent') {
            node.textContent = value;
        } else if (key === 'dataset') {
            for (const [dKey, dVal] of Object.entries(value)) {
                if (dVal !== undefined && dVal !== null) node.dataset[dKey] = String(dVal);
            }
        } else if (key === 'listeners') {
            for (const [eventName, handler] of Object.entries(value)) {
                node.addEventListener(eventName, handler);
            }
        } else if (value === true) {
            node.setAttribute(key, '');
        } else {
            node.setAttribute(key, String(value));
        }
    }
    for (const child of children.flat()) {
        if (child === null || child === undefined || child === false) continue;
        node.append(typeof child === 'string' ? document.createTextNode(child) : child);
    }
    return node;
}

function supporterErrorKey(body, status) {
    const detail = body && typeof body.detail === 'string' ? body.detail : '';
    if (detail === 'supporter_key_format') return 'supporter.error.format';
    if (detail === 'supporter_key_invalid') return 'supporter.error.invalid';
    if (status === 403) return 'supporter.error.readonly';
    return 'supporter.error.failed';
}

export function createSupporterSettings({ t, apiFetch, getLocale }) {
    const state = {
        doc: { ...DEFAULT_SUPPORTER_DOC },
        previewTier: 'personal',
        inFlight: false,
        mutationSeq: 0,
        statusKey: '',
        statusKind: '',
    };

    const panel = () => document.getElementById('tab-supporter');

    function syncHeaderAndTab() {
        const active = Boolean(state.doc.active);
        const tabBtn = document.getElementById('tab-supporter-btn');
        const tabDot = document.getElementById('tabSupporterDot');
        if (tabBtn) tabBtn.classList.toggle('is-active', active);
        if (tabDot) tabDot.hidden = !active;
        updateCachedSupporter(state.doc);
    }

    function setStatus(key, kind = '') {
        state.statusKey = key || '';
        state.statusKind = kind || '';
        const statusEl = document.getElementById('supporterActionStatus');
        if (!statusEl) return;
        statusEl.textContent = key ? t(key) : '';
        if (kind) statusEl.dataset.kind = kind;
        else statusEl.removeAttribute('data-kind');
    }

    function setControlsBusy(busy, action) {
        const input = document.getElementById('supporterKeyInput');
        const activateBtn = panel()?.querySelector('[data-supporter-activate]');
        const clearBtn = panel()?.querySelector('[data-supporter-clear]');
        const toggleBtn = document.getElementById('supporterShowHeaderToggle');
        if (input) input.disabled = busy;
        if (toggleBtn) toggleBtn.disabled = busy;
        if (activateBtn) {
            activateBtn.disabled = busy;
            activateBtn.textContent = t(
                busy && action === 'activate'
                    ? 'supporter.action.activating'
                    : 'supporter.action.activate',
            );
        }
        if (clearBtn) {
            clearBtn.disabled = busy;
            clearBtn.textContent = t(
                busy && action === 'remove'
                    ? 'supporter.action.removing'
                    : 'supporter.action.remove',
            );
        }
    }

    function buildKeyForm(canClear) {
        const input = el('input', {
            id: 'supporterKeyInput',
            type: 'text',
            className: 'supporter-key-input',
            autocomplete: 'off',
            spellcheck: 'false',
            placeholder: t('supporter.input.placeholder'),
            'aria-label': t('supporter.input.label'),
            dataset: { supporterInput: 'true' },
            listeners: {
                keydown: (event) => {
                    if (event.key !== 'Enter') return;
                    event.preventDefault();
                    event.stopPropagation();
                    submitKey(input.value);
                },
            },
        });
        const activateBtn = el('button', {
            type: 'button',
            className: 'primary-button',
            textContent: t('supporter.action.activate'),
            dataset: { supporterActivate: 'true' },
            listeners: {
                click: () => submitKey(input.value),
            },
        });
        const clearBtn = canClear
            ? el('button', {
                type: 'button',
                className: 'danger-button',
                textContent: t('supporter.action.remove'),
                dataset: { supporterClear: 'true' },
                listeners: {
                    click: () => clearKey(),
                },
            })
            : null;
        return el('div', { className: 'supporter-key-form' }, input, activateBtn, clearBtn);
    }

    function buildComposeHint() {
        const text = t('supporter.inactive.composeHint', { env: 'STATS_SUPPORTER_KEY' });
        const marker = 'STATS_SUPPORTER_KEY';
        const index = text.indexOf(marker);
        const hintChildren = [];
        if (index >= 0) {
            hintChildren.push(text.slice(0, index));
            hintChildren.push(el('code', { textContent: marker }));
            hintChildren.push(text.slice(index + marker.length));
        } else {
            hintChildren.push(text);
        }
        return el(
            'div',
            { className: 'supporter-inactive-foot' },
            el('span', {}, ...hintChildren),
            el('span', {
                className: 'supporter-inactive-offline',
                textContent: t('supporter.inactive.offlineNote'),
            }),
        );
    }

    function buildBrandBarPreview({ tier = 'personal', showBadge = true, interactive = false }) {
        const isPatron = tier === 'patron';
        const badgeLabel = t(isPatron ? 'supporter.badge.patron' : 'supporter.badge.personal');
        const badgeNode = el(
            'span',
            {
                className: `supporter-plate${isPatron ? ' is-patron' : ''}`,
                hidden: !showBadge,
                dataset: { supporterInlineBadge: 'true', tier },
            },
            createVinylGlyphSvg({ size: 12, tier }),
            el('span', {
                textContent: badgeLabel,
                dataset: { supporterInlineBadgeLabel: 'true' },
            }),
        );

        const ghostCluster = el(
            'div',
            { className: 'brandbar-preview-ghosts', 'aria-hidden': 'true' },
            el('span', { className: 'brandbar-ghost-pill wide' }),
            el('span', { className: 'brandbar-ghost-pill' }),
            el('span', { className: 'brandbar-ghost-dot' }),
        );

        const rightControl = interactive
            ? el(
                'div',
                {
                    className: 'supporter-preview-seg',
                    role: 'group',
                    'aria-label': t('supporter.preview.headerTitle'),
                },
                el('button', {
                    type: 'button',
                    className: 'supporter-preview-seg-btn',
                    'aria-pressed': !isPatron ? 'true' : 'false',
                    textContent: t('supporter.badge.personal'),
                    dataset: { supporterPreview: 'personal' },
                    listeners: { click: () => selectPreviewTier('personal') },
                }),
                el('button', {
                    type: 'button',
                    className: 'supporter-preview-seg-btn',
                    'aria-pressed': isPatron ? 'true' : 'false',
                    textContent: t('supporter.badge.patron'),
                    dataset: { supporterPreview: 'patron' },
                    listeners: { click: () => selectPreviewTier('patron') },
                }),
            )
            : ghostCluster;

        return el(
            'div',
            { className: 'supporter-brandbar-preview' },
            el(
                'div',
                { className: 'brandbar-preview-head' },
                el('span', {
                    className: 'brandbar-preview-caption',
                    textContent: t('supporter.preview.headerTitle'),
                }),
            ),
            el(
                'div',
                { className: 'brandbar-preview-bar' },
                el(
                    'div',
                    { className: 'brandbar-preview-brand' },
                    createMiniBrandMarkSvg({ size: 18 }),
                    el('span', { className: 'brandbar-preview-wordmark', textContent: 'Navidrome Stat' }),
                    badgeNode,
                ),
                rightControl,
            ),
        );
    }

    function buildShowcaseCard() {
        const tier = state.previewTier === 'patron' ? 'patron' : 'personal';
        const ctaLink = el(
            'a',
            {
                className: 'supporter-cta-btn',
                href: supportUrl(getLocale()),
                target: '_blank',
                rel: 'noopener noreferrer',
            },
            createVinylGlyphSvg({ size: 13, tier }),
            el('span', { textContent: t('supporter.showcase.cta') }),
            el('span', { 'aria-hidden': 'true', textContent: '↗' }),
        );

        return el(
            'section',
            { className: 'supporter-plaque supporter-showcase' },
            el(
                'div',
                { className: 'plaque-top' },
                el(
                    'div',
                    { className: 'plaque-emblem' },
                    createPlaqueVinylEmblemSvg({ tier, size: 60 }),
                ),
                el(
                    'div',
                    { className: 'plaque-meta' },
                    el('div', {
                        className: 'plaque-eyebrow',
                        textContent: t('supporter.plaque.eyebrow'),
                    }),
                    el(
                        'div',
                        { className: 'plaque-title-row' },
                        el('h2', {
                            className: 'plaque-title',
                            textContent: t('supporter.showcase.title'),
                        }),
                    ),
                    el('p', {
                        className: 'plaque-thanks',
                        textContent: t('supporter.inactive.lead'),
                    }),
                    el(
                        'div',
                        { className: 'supporter-showcase-pillars' },
                        el(
                            'span',
                            {},
                            el('i', { 'aria-hidden': 'true' }),
                            el('span', {
                                textContent: t(
                                    tier === 'patron'
                                        ? 'supporter.showcase.pillarOneTimePatron'
                                        : 'supporter.showcase.pillarOneTime',
                                ),
                            }),
                        ),
                        el(
                            'span',
                            {},
                            el('i', { 'aria-hidden': 'true' }),
                            el('span', { textContent: t('supporter.showcase.pillarThemes') }),
                        ),
                        el(
                            'span',
                            {},
                            el('i', { 'aria-hidden': 'true' }),
                            el('span', { textContent: t('supporter.showcase.pillarOffline') }),
                        ),
                    ),
                ),
            ),
            el(
                'div',
                { className: 'supporter-plaque-body' },
                buildBrandBarPreview({ tier, showBadge: true, interactive: true }),
            ),
            el(
                'div',
                { className: 'supporter-showcase-cta' },
                ctaLink,
                el('span', {
                    className: 'supporter-cta-note',
                    textContent: t('supporter.showcase.tiersNote'),
                }),
            ),
        );
    }

    function buildActivePlaque() {
        const s = state.doc;
        const tier = s.tier === 'patron' ? 'patron' : 'personal';
        const tierKey = tier === 'patron' ? 'supporter.tier.patron' : 'supporter.tier.personal';
        const thanksKey = tier === 'patron'
            ? 'supporter.plaque.thanksPatron'
            : 'supporter.plaque.thanksPersonal';
        const originKey = s.origin === 'env' ? 'supporter.origin.env' : 'supporter.origin.db';

        const metaRow = (labelKey, value) => el(
            'div',
            { className: 'about-row' },
            el('dt', { textContent: t(labelKey) }),
            el('dd', { textContent: value }),
        );

        return el(
            'section',
            { className: `supporter-plaque is-activated${tier === 'patron' ? ' is-patron' : ''}` },
            el(
                'div',
                { className: 'plaque-top' },
                el(
                    'div',
                    { className: 'plaque-emblem' },
                    createPlaqueVinylEmblemSvg({ tier, size: 60 }),
                ),
                el(
                    'div',
                    { className: 'plaque-meta' },
                    el('div', {
                        className: 'plaque-eyebrow',
                        textContent: t('supporter.plaque.eyebrow'),
                    }),
                    el(
                        'div',
                        { className: 'plaque-title-row' },
                        el('h2', { className: 'plaque-title', textContent: t(tierKey) }),
                        el(
                            'span',
                            { className: 'plaque-tier-tag' },
                            createVinylGlyphSvg({ size: 11, tier }),
                            el('span', { textContent: t('supporter.plaque.lit') }),
                        ),
                        s.issued_at
                            ? el('span', {
                                className: 'plaque-since',
                                textContent: t('supporter.plaque.since', { date: s.issued_at }),
                            })
                            : null,
                    ),
                    el('p', { className: 'plaque-thanks', textContent: t(thanksKey) }),
                ),
            ),
            el(
                'div',
                { className: 'supporter-plaque-body' },
                buildBrandBarPreview({
                    tier,
                    showBadge: s.show_in_header !== false,
                    interactive: false,
                }),
                el(
                    'div',
                    { className: 'supporter-receipt' },
                    el('span', { className: 'rk', textContent: s.key_preview || 'NS1.…' }),
                    el('span', { className: 'rv', textContent: `✓ ${t('supporter.plaque.verified')}` }),
                ),
                el(
                    'dl',
                    { className: 'about-list supporter-colophon' },
                    metaRow('supporter.plaque.tierLabel', t(tierKey)),
                    metaRow('supporter.plaque.orderLabel', s.order_preview || '—'),
                    metaRow('supporter.plaque.originLabel', t(originKey)),
                ),
            ),
        );
    }

    function buildManageSection(wasDetailsOpen) {
        const s = state.doc;
        const showHeader = s.show_in_header !== false;
        const switchBtn = el('button', {
            id: 'supporterShowHeaderToggle',
            type: 'button',
            className: 'switch',
            role: 'switch',
            'aria-checked': showHeader ? 'true' : 'false',
            'aria-label': t('supporter.showHeader.label'),
            listeners: {
                click: () => toggleShowHeader(),
            },
        });
        const toggleRow = el(
            'div',
            { className: 'setting-row' },
            el(
                'div',
                { className: 'setting-copy' },
                el('strong', { textContent: t('supporter.showHeader.label') }),
                el('span', { textContent: t('supporter.showHeader.help') }),
            ),
            switchBtn,
        );

        const details = el(
            'details',
            { className: 'supporter-manage', open: wasDetailsOpen },
            el('summary', { textContent: t('supporter.manage.summary') }),
            el(
                'div',
                { className: 'supporter-manage-body' },
                s.origin === 'env'
                    ? el('p', {
                        className: 'supporter-env-hint',
                        textContent: t('supporter.manage.envOverrideHint'),
                    })
                    : null,
                buildKeyForm(Boolean(s.can_clear)),
            ),
        );

        const statusNode = el('p', {
            id: 'supporterActionStatus',
            className: 'source-message supporter-action-status',
            role: 'status',
            'aria-live': 'polite',
            hidden: !state.statusKey,
            textContent: state.statusKey ? t(state.statusKey) : '',
            dataset: state.statusKind ? { kind: state.statusKind } : {},
        });

        return el('section', { className: 'settings-section supporter-manage-section' }, toggleRow, details, statusNode);
    }

    function buildInactiveSection() {
        const s = state.doc;
        let alertNode = null;
        if (s.status === 'invalid') {
            const alertKey = s.origin === 'env' ? 'supporter.invalid.env' : 'supporter.invalid.db';
            const clearBtn = s.origin === 'db' && s.can_clear
                ? el('button', {
                    type: 'button',
                    className: 'danger-button',
                    textContent: t('supporter.action.remove'),
                    dataset: { supporterClear: 'true' },
                    listeners: {
                        click: () => clearKey(),
                    },
                })
                : null;
            alertNode = el(
                'div',
                { className: 'supporter-alert', role: 'alert' },
                el('p', { textContent: t(alertKey) }),
                clearBtn,
            );
        }

        const statusNode = el('p', {
            id: 'supporterActionStatus',
            className: 'source-message supporter-action-status',
            role: 'status',
            'aria-live': 'polite',
            hidden: !state.statusKey,
            textContent: state.statusKey ? t(state.statusKey) : '',
            dataset: state.statusKind ? { kind: state.statusKind } : {},
        });

        return el(
            'section',
            { className: 'settings-section supporter-inactive' },
            el(
                'div',
                { className: 'section-heading' },
                el(
                    'div',
                    {},
                    el('h3', { textContent: t('supporter.inactive.haveKeyTitle') }),
                    el('p', { textContent: t('supporter.inactive.haveKeyHelp') }),
                ),
            ),
            alertNode,
            buildKeyForm(false),
            statusNode,
            buildComposeHint(),
        );
    }

    function captureFocusTarget(container) {
        const activeEl = document.activeElement;
        if (!activeEl || !container.contains(activeEl)) return null;
        if (activeEl.id) return `#${activeEl.id}`;
        if (activeEl.dataset?.supporterPreview) {
            return `[data-supporter-preview="${activeEl.dataset.supporterPreview}"]`;
        }
        if (activeEl.dataset?.supporterActivate) return '[data-supporter-activate]';
        if (activeEl.dataset?.supporterClear) return '[data-supporter-clear]';
        if (activeEl.tagName === 'SUMMARY') return '.supporter-manage > summary';
        return null;
    }

    function render(explicitFocusSelector = null) {
        const container = panel();
        if (!container) return;

        const focusSelector = explicitFocusSelector || captureFocusTarget(container);
        const existingInput = document.getElementById('supporterKeyInput');
        const preservedDraft = existingInput ? existingInput.value : '';
        const existingDetails = container.querySelector('.supporter-manage');
        const wasDetailsOpen = Boolean(existingDetails?.open);

        if (state.doc.active) {
            container.replaceChildren(
                buildActivePlaque(),
                buildManageSection(wasDetailsOpen),
            );
        } else {
            const showcase = buildShowcaseCard();
            const inactiveSection = buildInactiveSection();
            container.replaceChildren(
                ...(state.doc.status === 'invalid'
                    ? [inactiveSection, showcase]
                    : [showcase, inactiveSection]),
            );
        }

        const nextInput = document.getElementById('supporterKeyInput');
        if (nextInput && preservedDraft) nextInput.value = preservedDraft;

        const statusEl = document.getElementById('supporterActionStatus');
        if (statusEl) {
            statusEl.hidden = !state.statusKey;
        }

        if (focusSelector) {
            const nextFocus = container.querySelector(focusSelector);
            if (nextFocus && typeof nextFocus.focus === 'function') {
                nextFocus.focus({ preventScroll: true });
            }
        }
    }

    function selectPreviewTier(nextTier) {
        if (state.doc.active) return;
        const normalized = nextTier === 'patron' ? 'patron' : 'personal';
        if (state.previewTier === normalized) return;
        state.previewTier = normalized;
        render();
    }

    function clearPreview() {
        if (state.previewTier === 'personal') return false;
        state.previewTier = 'personal';
        if (!state.doc.active) render();
        return true;
    }

    async function submitKey(rawKey) {
        if (state.inFlight) return false;
        const trimmed = String(rawKey || '').trim();
        if (!trimmed) {
            setStatus('supporter.error.empty', 'error');
            const statusEl = document.getElementById('supporterActionStatus');
            if (statusEl) statusEl.hidden = false;
            return false;
        }
        state.inFlight = true;
        setControlsBusy(true, 'activate');
        setStatus('');
        try {
            const response = await apiFetch('/api/supporter-key', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: trimmed }),
            });
            const body = await response.json().catch(() => null);
            if (!response.ok || !body?.supporter?.active) {
                setControlsBusy(false, 'activate');
                setStatus(supporterErrorKey(body, response.status), 'error');
                const statusEl = document.getElementById('supporterActionStatus');
                if (statusEl) statusEl.hidden = false;
                return false;
            }
            state.mutationSeq += 1;
            state.doc = body.supporter;
            state.previewTier = 'personal';
            state.statusKey = 'supporter.status.activated';
            state.statusKind = 'success';
            const input = document.getElementById('supporterKeyInput');
            if (input) input.value = '';
            syncHeaderAndTab();
            render();
            return true;
        } catch (error) {
            if (error instanceof UnauthorizedError) throw error;
            setControlsBusy(false, 'activate');
            setStatus('supporter.error.failed', 'error');
            const statusEl = document.getElementById('supporterActionStatus');
            if (statusEl) statusEl.hidden = false;
            return false;
        } finally {
            state.inFlight = false;
        }
    }

    async function clearKey() {
        if (state.inFlight) return false;
        state.inFlight = true;
        setControlsBusy(true, 'remove');
        setStatus('');
        try {
            const response = await apiFetch('/api/supporter-key', { method: 'DELETE' });
            const body = await response.json().catch(() => null);
            if (!response.ok || !body?.supporter) {
                setControlsBusy(false, 'remove');
                setStatus(supporterErrorKey(body, response.status), 'error');
                const statusEl = document.getElementById('supporterActionStatus');
                if (statusEl) statusEl.hidden = false;
                return false;
            }
            state.mutationSeq += 1;
            state.doc = body.supporter;
            state.previewTier = 'personal';
            state.statusKey = 'supporter.status.removed';
            state.statusKind = 'success';
            const input = document.getElementById('supporterKeyInput');
            if (input) input.value = '';
            syncHeaderAndTab();
            render();
            return true;
        } catch (error) {
            if (error instanceof UnauthorizedError) throw error;
            setControlsBusy(false, 'remove');
            setStatus('supporter.error.failed', 'error');
            const statusEl = document.getElementById('supporterActionStatus');
            if (statusEl) statusEl.hidden = false;
            return false;
        } finally {
            state.inFlight = false;
        }
    }

    async function toggleShowHeader() {
        if (state.inFlight) return false;
        const container = panel();
        const restoreFocus = container ? captureFocusTarget(container) : null;
        const nextShow = !(state.doc.show_in_header !== false);
        state.inFlight = true;
        setControlsBusy(true, 'toggle');
        try {
            const response = await apiFetch('/api/supporter/preferences', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ show_in_header: nextShow }),
            });
            const body = await response.json().catch(() => null);
            if (!response.ok || !body?.supporter) {
                setStatus('supporter.error.failed', 'error');
                const statusEl = document.getElementById('supporterActionStatus');
                if (statusEl) statusEl.hidden = false;
                return false;
            }
            state.mutationSeq += 1;
            state.doc = body.supporter;
            state.statusKey = 'supporter.status.displayUpdated';
            state.statusKind = 'success';
            syncHeaderAndTab();
            render(restoreFocus);
            return true;
        } catch (error) {
            if (error instanceof UnauthorizedError) throw error;
            setStatus('supporter.error.failed', 'error');
            const statusEl = document.getElementById('supporterActionStatus');
            if (statusEl) statusEl.hidden = false;
            return false;
        } finally {
            state.inFlight = false;
            setControlsBusy(false, 'toggle');
            if (restoreFocus) {
                const target = panel()?.querySelector(restoreFocus);
                if (target && typeof target.focus === 'function') {
                    target.focus({ preventScroll: true });
                }
            }
        }
    }

    async function load() {
        const seqAtStart = state.mutationSeq;
        try {
            const response = await apiFetch('/api/supporter');
            if (!response.ok) return;
            const body = await response.json();
            if (seqAtStart !== state.mutationSeq) return;
            if (body?.supporter) {
                state.doc = body.supporter;
                syncHeaderAndTab();
                render();
            }
        } catch (error) {
            if (error instanceof UnauthorizedError) throw error;
        }
    }

    function mount() {
        syncHeaderAndTab();
        render();
    }

    function localize() {
        syncHeaderAndTab();
        render();
    }

    return {
        mount,
        load,
        localize,
        clearPreview,
    };
}
