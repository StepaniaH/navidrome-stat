/**
 * ECharts theme tokens shared by every dashboard chart.
 *
 * Colors follow the active theme's panel/border/text values so charts can be
 * re-themed without a page reload.
 */

export const chartPalette = ['#a78bfa', '#818cf8', '#34d399', '#f472b6', '#fb923c', '#facc15', '#22d3ee', '#f87171'];

const THEME_CHART_COLORS = {
    frappe: { text: '#a5adce', tooltipBg: '#292c3c', tooltipBorder: '#51576d', tooltipText: '#c6d0f5' },
    latte: { text: '#5c5f77', tooltipBg: '#e6e9ef', tooltipBorder: '#bcc0cc', tooltipText: '#4c4f69' },
    macchiato: { text: '#a5adcb', tooltipBg: '#1e2030', tooltipBorder: '#494d64', tooltipText: '#cad3f5' },
    mocha: { text: '#a6adc8', tooltipBg: '#181825', tooltipBorder: '#45475a', tooltipText: '#cdd6f4' },
    nord: { text: '#b8c2d1', tooltipBg: '#3b4252', tooltipBorder: '#4c566a', tooltipText: '#eceff4' },
    dracula: { text: '#b8bfce', tooltipBg: '#21222c', tooltipBorder: '#6272a4', tooltipText: '#f8f8f2' },
    'tokyo-night': { text: '#a9b1d6', tooltipBg: '#16161e', tooltipBorder: '#414868', tooltipText: '#c0caf5' },
    'gruvbox-dark': { text: '#d5c4a1', tooltipBg: '#1d2021', tooltipBorder: '#504945', tooltipText: '#ebdbb2' },
    'solarized-dark': { text: '#839496', tooltipBg: '#073642', tooltipBorder: '#1a5561', tooltipText: '#93a1a1' },
    'solarized-light': { text: '#657b83', tooltipBg: '#eee8d5', tooltipBorder: '#cfc8b2', tooltipText: '#586e75' },
};

export function createThemeTokens(theme = document.documentElement.dataset.theme) {
    const colors = THEME_CHART_COLORS[theme] || THEME_CHART_COLORS.frappe;
    return {
        backgroundColor: 'transparent',
        textStyle: { color: colors.text, fontFamily: 'system-ui, sans-serif' },
        tooltip: {
            backgroundColor: colors.tooltipBg,
            borderColor: colors.tooltipBorder,
            textStyle: { color: colors.tooltipText, fontSize: 12 },
        },
    };
}
