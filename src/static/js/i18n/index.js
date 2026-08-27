// Locale registry: one module per language under ./locales, each exporting
// dashboard/review/settings string tables as [key, value] pairs. Pages derive
// their catalogs with pageMessages(...) so adding a language never touches
// page code.
import de from './locales/de.js';
import en from './locales/en.js';
import es from './locales/es.js';
import fr from './locales/fr.js';
import ja from './locales/ja.js';
import zhCN from './locales/zh-CN.js';
import zhTW from './locales/zh-TW.js';

const localeModules = {
    'zh-CN': zhCN,
    'zh-TW': zhTW,
    en,
    ja,
    de,
    es,
    fr,
};

export function pageMessages(...domains) {
    const messages = {};
    for (const [code, tables] of Object.entries(localeModules)) {
        messages[code] = Object.fromEntries(
            domains.flatMap((domain) => tables[domain] ?? []),
        );
    }
    return messages;
}
