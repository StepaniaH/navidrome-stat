(function initNavidromeLocalization(global) {
    'use strict';

    const DEFAULT_LOCALE = 'en';
    const LANGUAGE_STORAGE_KEY = 'navidrome-language';

    function readPreference(key, fallback = null) {
        try {
            const value = global.localStorage.getItem(key);
            return value === null ? fallback : value;
        } catch (_error) {
            return fallback;
        }
    }

    function writePreference(key, value) {
        try {
            global.localStorage.setItem(key, value);
            return true;
        } catch (_error) {
            return false;
        }
    }

    function removePreference(key) {
        try {
            global.localStorage.removeItem(key);
            return true;
        } catch (_error) {
            return false;
        }
    }

    function normalizeLocale(candidate, supportedLocales, fallbackLocale = DEFAULT_LOCALE) {
        const supported = Array.from(supportedLocales || []);
        if (supported.length === 0) return fallbackLocale;

        const value = String(candidate || '').trim();
        const exact = supported.find((locale) => locale === value);
        if (exact) return exact;

        const lower = value.toLowerCase();
        const caseInsensitive = supported.find((locale) => locale.toLowerCase() === lower);
        if (caseInsensitive) return caseInsensitive;

        const language = lower.split('-')[0];
        const languageMatch = supported.find(
            (locale) => locale.toLowerCase().split('-')[0] === language,
        );
        if (languageMatch) return languageMatch;

        return supported.includes(fallbackLocale) ? fallbackLocale : supported[0];
    }

    function interpolate(template, values = {}) {
        return String(template).replace(/\{([a-zA-Z0-9_]+)\}/g, (match, key) => {
            if (!Object.prototype.hasOwnProperty.call(values, key)) return match;
            const value = values[key];
            return value === null || value === undefined ? '' : String(value);
        });
    }

    function createI18n({
        messages,
        fallbackLocale = DEFAULT_LOCALE,
        storageKey = LANGUAGE_STORAGE_KEY,
        initialLocale,
    }) {
        if (!messages || typeof messages !== 'object') {
            throw new TypeError('messages must be an object keyed by locale');
        }

        const supportedLocales = Object.freeze(Object.keys(messages));
        const fallback = normalizeLocale(fallbackLocale, supportedLocales, DEFAULT_LOCALE);
        let locale = normalizeLocale(
            initialLocale || readPreference(storageKey, fallback),
            supportedLocales,
            fallback,
        );
        const listeners = new Set();

        function t(key, values = {}) {
            const localizedMessage = messages[locale] && messages[locale][key];
            const fallbackMessage = messages[fallback] && messages[fallback][key];
            return interpolate(localizedMessage ?? fallbackMessage ?? key, values);
        }

        function translateElement(element) {
            if (element.dataset.i18n) {
                element.textContent = t(element.dataset.i18n);
            }
            if (!element.dataset.i18nAttr) return;

            element.dataset.i18nAttr.split(',').forEach((definition) => {
                const separator = definition.indexOf(':');
                if (separator < 1) return;
                const attribute = definition.slice(0, separator).trim();
                const key = definition.slice(separator + 1).trim();
                if (attribute && key) element.setAttribute(attribute, t(key));
            });
        }

        function translate(root = global.document) {
            if (!root) return;
            global.document.documentElement.lang = locale;
            if (root.nodeType === 1 && (root.dataset.i18n || root.dataset.i18nAttr)) {
                translateElement(root);
            }
            root.querySelectorAll('[data-i18n], [data-i18n-attr]').forEach(translateElement);
        }

        function setLocale(nextLocale, { persist = true, translateDom = true } = {}) {
            const normalized = normalizeLocale(nextLocale, supportedLocales, fallback);
            const changed = normalized !== locale;
            locale = normalized;
            if (persist) writePreference(storageKey, normalized);
            if (translateDom) translate();
            if (changed) listeners.forEach((listener) => listener(normalized));
            return normalized;
        }

        function subscribe(listener) {
            listeners.add(listener);
            return () => listeners.delete(listener);
        }

        function formatNumber(value, options) {
            return new Intl.NumberFormat(locale, options).format(Number(value) || 0);
        }

        function formatDate(value, options) {
            return new Intl.DateTimeFormat(locale, options).format(value);
        }

        return Object.freeze({
            formatDate,
            formatNumber,
            getLocale: () => locale,
            messages,
            setLocale,
            subscribe,
            supportedLocales,
            t,
            translate,
        });
    }

    global.NavidromeI18n = Object.freeze({
        DEFAULT_LOCALE,
        LANGUAGE_STORAGE_KEY,
        createI18n,
        interpolate,
        normalizeLocale,
        readPreference,
        removePreference,
        writePreference,
    });
}(window));
