/**
 * Shared supporter URL, pressed dubplate vinyl SVG artwork, and badge synchronization helpers.
 *
 * Uses safe DOM and SVG element creation APIs only (never raw HTML markup strings).
 */

import { LOCALE_CODES } from './locales.js';

export const SUPPORT_ORIGIN = 'https://navidrome-stat.stepaniah.me/';
export const SUPPORT_HASH = '#support';
export const SUPPORT_URL = `${SUPPORT_ORIGIN}${SUPPORT_HASH}`;

const SVG_NS = 'http://www.w3.org/2000/svg';
const LOCALE_CODE_RE = /^[a-z]{2}(?:-[A-Za-z0-9]{2,8})*$/;
const SUPPORTED_LOCALE_SET = new Set(LOCALE_CODES);

let svgIdSeq = 0;

export function supportUrl(locale = '') {
    const raw = String(locale || '').trim();
    if (!raw || raw === 'auto' || !LOCALE_CODE_RE.test(raw)) return SUPPORT_URL;
    if (!SUPPORTED_LOCALE_SET.has(raw)) return SUPPORT_URL;
    return `${SUPPORT_ORIGIN}?lang=${encodeURIComponent(raw)}${SUPPORT_HASH}`;
}

export function svgEl(tag, attrs = {}) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs)) {
        if (value !== undefined && value !== null) {
            node.setAttribute(key, String(value));
        }
    }
    return node;
}

/**
 * Dimensional 16x16 pressed dubplate pin for top-bar badges and inline buttons.
 * Uses <circle> and <path> exclusively (never <ellipse>).
 */
export function createVinylGlyphSvg({
    size = 13,
    className = 'vinyl-glyph',
    tier = 'personal',
} = {}) {
    const svg = svgEl('svg', {
        class: className,
        width: size,
        height: size,
        viewBox: '0 0 16 16',
        fill: 'none',
        'aria-hidden': 'true',
        'data-vinyl-tier': tier === 'patron' ? 'patron' : 'personal',
    });
    svg.append(
        svgEl('circle', {
            cx: 8,
            cy: 8,
            r: 6.75,
            fill: '#111620',
            stroke: 'currentColor',
            'stroke-opacity': 0.56,
            'stroke-width': 1,
        }),
        svgEl('circle', {
            cx: 8,
            cy: 8,
            r: 5.05,
            stroke: '#ffffff',
            'stroke-opacity': 0.16,
            'stroke-width': 0.65,
        }),
        svgEl('path', {
            d: 'M 4.15 5.05 A 4.85 4.85 0 0 1 10.95 4.15',
            stroke: '#ffffff',
            'stroke-opacity': 0.36,
            'stroke-width': 0.9,
            'stroke-linecap': 'round',
        }),
        svgEl('path', {
            d: 'M 11.85 10.95 A 4.85 4.85 0 0 1 5.05 11.85',
            stroke: '#ffffff',
            'stroke-opacity': 0.28,
            'stroke-width': 0.85,
            'stroke-linecap': 'round',
        }),
        svgEl('circle', {
            cx: 8,
            cy: 8,
            r: 2.85,
            fill: 'currentColor',
        }),
    );
    if (tier === 'patron') {
        svg.append(
            svgEl('circle', {
                cx: 8,
                cy: 8,
                r: 3.7,
                stroke: 'currentColor',
                'stroke-opacity': 0.68,
                'stroke-width': 0.55,
            }),
        );
    }
    svg.append(
        svgEl('circle', {
            cx: 8,
            cy: 8,
            r: 0.82,
            fill: '#111620',
        }),
    );
    return svg;
}

/**
 * Dimensional 64x64 audiophile lacquer dubplate & duotone anodized center label
 * for the Settings -> Supporter collector's plaque.
 */
export function createPlaqueVinylEmblemSvg({ tier = 'personal', size = 60 } = {}) {
    const uid = ++svgIdSeq;
    const discGradId = `ns-vinyl-disc-${uid}`;
    const labelGradId = `ns-vinyl-label-${uid}`;
    const rimGradId = `ns-vinyl-rim-${uid}`;

    const svg = svgEl('svg', {
        class: 'plaque-logo',
        width: size,
        height: size,
        viewBox: '0 0 64 64',
        fill: 'none',
        'aria-hidden': 'true',
    });

    const defs = svgEl('defs');

    const discGrad = svgEl('radialGradient', {
        id: discGradId,
        cx: '34%',
        cy: '28%',
        r: '72%',
    });
    discGrad.append(
        svgEl('stop', { offset: '0%', 'stop-color': '#252e3d' }),
        svgEl('stop', { offset: '56%', 'stop-color': '#0f141d' }),
        svgEl('stop', { offset: '100%', 'stop-color': '#18202c' }),
    );

    const labelGrad = svgEl('linearGradient', {
        id: labelGradId,
        x1: '18',
        y1: '18',
        x2: '46',
        y2: '46',
        gradientUnits: 'userSpaceOnUse',
    });
    labelGrad.append(
        svgEl('stop', { offset: '0%', 'stop-color': 'var(--sup-hi)' }),
        svgEl('stop', { offset: '52%', 'stop-color': 'var(--sup-main)' }),
        svgEl('stop', { offset: '100%', 'stop-color': 'var(--sup-sec)' }),
    );

    const rimGrad = svgEl('linearGradient', {
        id: rimGradId,
        x1: '6',
        y1: '6',
        x2: '58',
        y2: '58',
        gradientUnits: 'userSpaceOnUse',
    });
    rimGrad.append(
        svgEl('stop', { offset: '0%', 'stop-color': 'var(--sup-hi)', 'stop-opacity': '0.65' }),
        svgEl('stop', { offset: '50%', 'stop-color': '#ffffff', 'stop-opacity': '0.16' }),
        svgEl('stop', { offset: '100%', 'stop-color': 'var(--sup-sec)', 'stop-opacity': '0.45' }),
    );

    defs.append(discGrad, labelGrad, rimGrad);
    svg.append(defs);

    // Lacquer disc body + machined outer chamfer
    svg.append(
        svgEl('circle', {
            cx: 32,
            cy: 32,
            r: 30,
            fill: `url(#${discGradId})`,
            stroke: `url(#${rimGradId})`,
            'stroke-width': 1.2,
        }),
        svgEl('circle', {
            cx: 32,
            cy: 32,
            r: 28.6,
            stroke: '#ffffff',
            'stroke-opacity': 0.09,
            'stroke-width': 0.6,
        }),
        // Conical silk-sheen light wedges across spun grooves
        svgEl('path', {
            d: 'M 32 32 L 12.2 10.6 A 29 29 0 0 1 25.4 3.8 Z',
            fill: '#ffffff',
            'fill-opacity': 0.075,
        }),
        svgEl('path', {
            d: 'M 32 32 L 51.8 53.4 A 29 29 0 0 1 38.6 60.2 Z',
            fill: '#ffffff',
            'fill-opacity': 0.055,
        }),
    );

    // 6 concentric precision micro-grooves
    const grooveRadii = [26.6, 24.1, 21.6, 19.1, 16.6, 14.3];
    grooveRadii.forEach((radius, idx) => {
        svg.append(
            svgEl('circle', {
                cx: 32,
                cy: 32,
                r: radius,
                stroke: '#ffffff',
                'stroke-opacity': idx % 2 === 0 ? 0.12 : 0.065,
                'stroke-width': 0.65,
            }),
        );
    });

    // Specular groove highlight arcs + matrix run-out ring + duotone anodized label
    svg.append(
        svgEl('path', {
            d: 'M 13.8 20.4 A 21.6 21.6 0 0 1 43.6 13.8',
            stroke: '#ffffff',
            'stroke-opacity': 0.24,
            'stroke-width': 1.05,
            'stroke-linecap': 'round',
        }),
        svgEl('path', {
            d: 'M 50.2 43.6 A 21.6 21.6 0 0 1 20.4 50.2',
            stroke: '#ffffff',
            'stroke-opacity': 0.16,
            'stroke-width': 0.95,
            'stroke-linecap': 'round',
        }),
        svgEl('circle', {
            cx: 32,
            cy: 32,
            r: 12.4,
            stroke: 'var(--sup-hi)',
            'stroke-opacity': 0.38,
            'stroke-width': 0.65,
        }),
        svgEl('circle', {
            cx: 32,
            cy: 32,
            r: 10.8,
            fill: `url(#${labelGradId})`,
        }),
        svgEl('circle', {
            cx: 32,
            cy: 32,
            r: 8.1,
            stroke: '#0b0f17',
            'stroke-opacity': 0.3,
            'stroke-width': 0.65,
        }),
    );

    if (tier === 'patron') {
        svg.append(
            svgEl('circle', {
                cx: 32,
                cy: 32,
                r: 6.25,
                stroke: '#0b0f17',
                'stroke-opacity': 0.28,
                'stroke-width': 0.6,
                'stroke-dasharray': '1.6 1.2',
            }),
        );
    }

    // Center spindle bushing & hole
    svg.append(
        svgEl('circle', {
            cx: 32,
            cy: 32,
            r: 3.1,
            fill: '#0f141d',
            'fill-opacity': 0.42,
        }),
        svgEl('circle', {
            cx: 32,
            cy: 32,
            r: 1.85,
            fill: '#0c1017',
        }),
    );

    return svg;
}

/**
 * Miniature Navidrome Stat brand mark for inline top-bar preview in Settings.
 */
export function createMiniBrandMarkSvg({ size = 18 } = {}) {
    const svg = svgEl('svg', {
        class: 'preview-brand-mark',
        width: size,
        height: size,
        viewBox: '0 0 32 32',
        fill: 'none',
        'aria-hidden': 'true',
    });
    svg.append(
        svgEl('path', {
            d: 'M 25.2 14.2 A 9.6 9.6 0 1 0 21.8 22.8',
            stroke: 'var(--text)',
            'stroke-width': 2.1,
            'stroke-linecap': 'round',
        }),
        svgEl('circle', {
            cx: 15,
            cy: 17.5,
            r: 2.3,
            stroke: 'var(--text)',
            'stroke-width': 1.8,
        }),
        svgEl('path', {
            d: 'M 17.2 17.5 V 9.2 L 21.5 10.8 V 13.6 L 17.2 12',
            stroke: 'var(--text)',
            'stroke-width': 1.8,
            'stroke-linecap': 'round',
            'stroke-linejoin': 'round',
        }),
        svgEl('path', {
            d: 'M 18 23.2 L 21.2 20.5 L 25.2 17.5',
            stroke: 'var(--accent)',
            'stroke-width': 2,
            'stroke-linecap': 'round',
            'stroke-linejoin': 'round',
        }),
        svgEl('circle', {
            cx: 25.2,
            cy: 17.5,
            r: 1.4,
            fill: 'var(--accent)',
        }),
    );
    return svg;
}

export function syncSupporterPlate({
    header = null,
    headerClass = 'has-supporter-vinyl',
    badge = null,
    divider = null,
    label = null,
    footerLink = null,
    footerLabel = null,
    supporter = null,
    previewing = false,
    t,
    locale = 'en',
    internalHref = '/settings#supporter',
    externalOnly = false,
} = {}) {
    const info = supporter && typeof supporter === 'object' ? supporter : {};
    const active = Boolean(info.active);
    const isPreview = !active && Boolean(previewing);
    const showInHeader = info.show_in_header !== false;
    const showBadge = (active && showInHeader) || isPreview;
    const tier = info.tier === 'patron' ? 'patron' : 'personal';

    if (header?.classList) {
        header.classList.toggle(headerClass, showBadge);
    }
    if (divider) {
        divider.hidden = !showBadge;
    }

    const destination = externalOnly ? supportUrl(locale) : internalHref;

    if (badge) {
        badge.hidden = !showBadge;
        badge.classList.toggle('is-patron', showBadge && !isPreview && tier === 'patron');
        if (badge.tagName === 'A') {
            badge.setAttribute('href', destination);
            if (externalOnly) {
                badge.setAttribute('target', '_blank');
                badge.setAttribute('rel', 'noopener noreferrer');
            } else {
                badge.removeAttribute('target');
                badge.removeAttribute('rel');
            }
        }
        if (showBadge) {
            const effectiveTier = isPreview ? 'personal' : tier;
            const existingGlyph = badge.querySelector('.vinyl-glyph');
            if (!existingGlyph || existingGlyph.getAttribute('data-vinyl-tier') !== effectiveTier) {
                const nextGlyph = createVinylGlyphSvg({
                    size: 13,
                    className: 'vinyl-glyph',
                    tier: effectiveTier,
                });
                if (existingGlyph) {
                    existingGlyph.replaceWith(nextGlyph);
                } else {
                    badge.prepend(nextGlyph);
                }
            }
            if (isPreview) {
                const shortLabel = t('supporter.badge.personal');
                const title = t('supporter.preview.headerTitle');
                if (label) label.textContent = shortLabel;
                badge.setAttribute('data-tier', 'personal');
                badge.setAttribute('data-preview', 'true');
                badge.setAttribute('title', title);
                badge.setAttribute('aria-label', title);
            } else {
                const shortLabel = t(
                    tier === 'patron' ? 'supporter.badge.patron' : 'supporter.badge.personal',
                );
                const tierName = t(
                    tier === 'patron' ? 'supporter.tier.patron' : 'supporter.tier.personal',
                );
                const title = info.issued_at
                    ? t('supporter.badge.title', { tier: tierName, date: info.issued_at })
                    : t('supporter.badge.titleNoDate', { tier: tierName });
                if (label) label.textContent = shortLabel;
                badge.setAttribute('data-tier', tier);
                badge.removeAttribute('data-preview');
                badge.setAttribute('title', title);
                badge.setAttribute('aria-label', title);
            }
        } else {
            badge.classList.remove('is-patron');
            badge.removeAttribute('data-tier');
            badge.removeAttribute('data-preview');
            badge.removeAttribute('title');
            badge.removeAttribute('aria-label');
        }
    }

    if (footerLink) {
        footerLink.classList.toggle('is-lit', active);
        if (footerLink.tagName === 'A') {
            footerLink.setAttribute('href', destination);
            if (externalOnly) {
                footerLink.setAttribute('target', '_blank');
                footerLink.setAttribute('rel', 'noopener noreferrer');
            } else {
                footerLink.removeAttribute('target');
                footerLink.removeAttribute('rel');
            }
        }
    }
    if (footerLabel) {
        if (active) {
            footerLabel.textContent = info.issued_at
                ? t('footer.supportingSince', { date: info.issued_at })
                : t('footer.supporting');
        } else {
            footerLabel.textContent = t('footer.support');
        }
    }
}
