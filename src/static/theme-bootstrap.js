import { readPreference } from './js/prefs.js';
import {
    APPEARANCE_PREFERENCE_KEYS,
    resolveAppearance,
} from './js/themes.js';

export const THEME_CHANGE_EVENT = 'navidrome:themechange';

const APPEARANCE_KEYS = new Set(Object.values(APPEARANCE_PREFERENCE_KEYS));
let colorSchemeQuery = null;

function prefersLightScheme() {
    try {
        colorSchemeQuery ||= window.matchMedia('(prefers-color-scheme: light)');
        return colorSchemeQuery.matches;
    } catch (_error) {
        return false;
    }
}

export function readStoredAppearance() {
    return resolveAppearance({
        legacyTheme: readPreference(APPEARANCE_PREFERENCE_KEYS.legacyTheme),
        mode: readPreference(APPEARANCE_PREFERENCE_KEYS.mode),
        palette: readPreference(APPEARANCE_PREFERENCE_KEYS.palette),
    }, prefersLightScheme());
}

export function applyStoredAppearance({ notify = true } = {}) {
    const appearance = readStoredAppearance();
    const root = document.documentElement;
    const changed = root.dataset.theme !== appearance.theme
        || root.dataset.scheme !== appearance.scheme
        || root.dataset.themeMode !== appearance.mode
        || root.dataset.palette !== appearance.palette;

    root.dataset.theme = appearance.theme;
    root.dataset.scheme = appearance.scheme;
    root.dataset.themeMode = appearance.mode;
    root.dataset.palette = appearance.palette;
    root.dataset.motion = readPreference('navidrome-motion', 'system') === 'reduced'
        ? 'reduced'
        : 'system';

    if (notify && changed) {
        window.dispatchEvent(new CustomEvent(THEME_CHANGE_EVENT, { detail: appearance }));
    }
    return appearance;
}

applyStoredAppearance({ notify: false });

window.addEventListener('storage', (event) => {
    if (event.key === null || APPEARANCE_KEYS.has(event.key)) applyStoredAppearance();
});

try {
    colorSchemeQuery ||= window.matchMedia('(prefers-color-scheme: light)');
    colorSchemeQuery.addEventListener('change', () => {
        if (readStoredAppearance().mode === 'system') applyStoredAppearance();
    });
} catch (_error) {
    // Older embedded browsers still get the initial resolved theme.
}
