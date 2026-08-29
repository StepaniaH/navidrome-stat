/**
 * ECharts tokens derived from the semantic CSS theme contract.
 *
 * Reading computed values keeps canvas charts aligned with the rest of the UI
 * for every concrete theme, including themes added after this module ships.
 */

const FALLBACK_PALETTE = [
    '#38bdf8', '#a78bfa', '#9bd65d', '#f7c65c',
    '#fb923c', '#f472b6', '#2dd4bf', '#ff7b86',
];

function cssToken(styles, name, fallback) {
    return styles.getPropertyValue(name).trim() || fallback;
}

export function colorWithAlpha(color, alpha) {
    const normalizedAlpha = Math.max(0, Math.min(1, Number(alpha) || 0));
    const normalizedColor = String(color).trim();
    const hex = normalizedColor.match(/^#([\da-f]{3}|[\da-f]{6})$/i)?.[1];
    if (hex) {
        const expanded = hex.length === 3
            ? hex.split('').map((part) => `${part}${part}`).join('')
            : hex;
        const red = Number.parseInt(expanded.slice(0, 2), 16);
        const green = Number.parseInt(expanded.slice(2, 4), 16);
        const blue = Number.parseInt(expanded.slice(4, 6), 16);
        return `rgba(${red}, ${green}, ${blue}, ${normalizedAlpha})`;
    }
    const rgb = normalizedColor.match(
        /^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*(?:0|1|0?\.\d+)\s*)?\)$/i,
    );
    if (rgb) {
        const channels = rgb.slice(1, 4).map((channel) => (
            Math.max(0, Math.min(255, Number.parseInt(channel, 10)))
        ));
        return `rgba(${channels.join(', ')}, ${normalizedAlpha})`;
    }
    return color;
}

export function createThemeTokens() {
    const styles = getComputedStyle(document.documentElement);
    const palette = FALLBACK_PALETTE.map((fallback, index) => (
        cssToken(styles, `--chart-${index + 1}`, fallback)
    ));
    const text = cssToken(styles, '--text-muted', '#b9c4d0');
    const dim = cssToken(styles, '--text-dim', '#93a1b1');
    const surface = cssToken(styles, '--surface', '#171e27');
    const raised = cssToken(styles, '--surface-raised', '#1d2631');
    const border = cssToken(styles, '--border', '#607086');
    const overlay = cssToken(styles, '--overlay', 'rgba(4, 9, 15, 0.72)');
    const tooltipBorder = colorWithAlpha(border, 0.46);
    const tooltipShadow = colorWithAlpha(overlay, 0.32);

    return Object.freeze({
        base: Object.freeze({
            backgroundColor: 'transparent',
            textStyle: { color: text, fontFamily: 'system-ui, sans-serif' },
            tooltip: {
                backgroundColor: raised,
                borderColor: tooltipBorder,
                borderWidth: 1,
                extraCssText: `box-shadow: 0 12px 30px -12px ${tooltipShadow}; border-radius: 8px;`,
                textStyle: { color: cssToken(styles, '--text', '#f1f5f9'), fontSize: 12 },
            },
        }),
        palette: Object.freeze(palette),
        axisText: dim,
        axisLine: border,
        gridLine: colorWithAlpha(border, 0.42),
        pieSeparator: colorWithAlpha(surface, 0.52),
        barGradient: Object.freeze([palette[1], palette[0]]),
        areaGradient: Object.freeze([
            colorWithAlpha(palette[2], 0.38),
            colorWithAlpha(palette[2], 0.03),
        ]),
        heatmap: Object.freeze([
            colorWithAlpha(palette[0], 0.08),
            colorWithAlpha(palette[0], 0.5),
            palette[0],
            palette[1],
        ]),
        shadow: colorWithAlpha(overlay, 0.28),
    });
}
