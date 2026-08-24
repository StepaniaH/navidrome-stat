import { readPreference } from './js/prefs.js';

document.documentElement.dataset.theme =
    readPreference('navidrome-theme', 'frappe');
document.documentElement.dataset.motion =
    readPreference('navidrome-motion', 'system') === 'reduced'
        ? 'reduced'
        : 'system';
