/**
 * ECharts theme tokens shared by every dashboard chart.
 *
 * Colors follow the Catppuccin palettes used by the CSS custom properties;
 * `createThemeTokens` reads the current `data-theme` attribute so charts can
 * be re-themed without a page reload.
 */

export const chartPalette = ['#a78bfa', '#818cf8', '#34d399', '#f472b6', '#fb923c', '#facc15', '#22d3ee', '#f87171'];

export function createThemeTokens(theme = document.documentElement.dataset.theme) {
    const latte = theme === 'latte';
    return {
        backgroundColor: 'transparent',
        textStyle: { color: latte ? '#5c5f77' : '#a5adce', fontFamily: 'system-ui, sans-serif' },
        tooltip: {
            backgroundColor: latte ? '#e6e9ef' : '#292c3c',
            borderColor: latte ? '#bcc0cc' : '#51576d',
            textStyle: { color: latte ? '#4c4f69' : '#c6d0f5', fontSize: 12 },
        },
    };
}
