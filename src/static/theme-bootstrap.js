import { readPreference } from './js/prefs.js';
import { resolveTheme, themeScheme } from './js/themes.js';

const theme = resolveTheme(readPreference('navidrome-theme', 'frappe'));
document.documentElement.dataset.theme = theme;
document.documentElement.dataset.scheme = themeScheme(theme);
document.documentElement.dataset.motion =
    readPreference('navidrome-motion', 'system') === 'reduced'
        ? 'reduced'
        : 'system';
