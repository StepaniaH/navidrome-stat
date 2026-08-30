import { apiFetch, isAbortError, UnauthorizedError, UNAUTHORIZED_EVENT } from './js/http.js';
import { createLoginController } from './js/auth.js';
import { readPreference, removePreference, writePreference } from './js/prefs.js';
import { createI18n } from './localization.js';
import { APPEARANCE_PREFERENCE_KEYS } from './js/themes.js';
import { createAppearanceSettings } from './js/settings/appearance-settings.js';
import { createConnectionSettings } from './js/settings/connection-settings.js';
import { createPrivacySettings } from './js/settings/privacy-settings.js';
import { SUPPORTED_LOCALES } from './js/locales.js';
import { applyAppVersion } from './js/app-info.js';
import { pageMessages } from './js/i18n/index.js';
import { createSelectListbox } from './js/listbox.js';

const preferenceKeys = Object.freeze({
    language: 'navidrome-language',
    timezone: 'navidrome-timezone',
    motion: 'navidrome-motion',
});

const i18n = createI18n({ messages: pageMessages('settings'), fallbackLocale: 'en' });
const t = (key, values) => i18n.t(key, values);
const listboxes = new Map();

function showBanner(kind, message) {
    const banner = document.getElementById('settingsBanner');
    banner.dataset.kind = kind;
    banner.textContent = message;
    banner.hidden = false;
}

function hideBanner() {
    document.getElementById('settingsBanner').hidden = true;
}

function getOptionLabel(option) {
    if (typeof option.label === 'function') return option.label();
    if (option.labelKey) return t(option.labelKey);
    return option.label || String(option.value);
}

function registerSettingsListbox(rootId, {
    placeholderKey = 'common.none',
    ...options
} = {}) {
    const root = document.getElementById(rootId);
    let currentPlaceholderKey = placeholderKey;
    const controller = createSelectListbox({
        root,
        placeholder: t(placeholderKey),
        getOptionLabel,
        getOptionSubtitle: (option) => (
            option.subtitleKey ? t(option.subtitleKey) : null
        ),
        optionClassName: 'settings-option',
        ...options,
    });
    const managedController = {
        ...controller,
        refreshLabels() {
            controller.refreshLabels({ placeholder: t(currentPlaceholderKey) });
        },
        setOptions(nextOptions, listOptions = {}) {
            currentPlaceholderKey = listOptions.placeholder ?? currentPlaceholderKey;
            controller.setOptions(nextOptions, {
                ...listOptions,
                placeholder: t(currentPlaceholderKey),
            });
        },
    };
    listboxes.set(rootId, managedController);
    return managedController;
}

const appearanceSettings = createAppearanceSettings({
    t,
    confirmDiscard: (message) => window.confirm(message),
});
const connectionSettings = createConnectionSettings({
    t,
    apiFetch,
    confirmDelete: (message) => window.confirm(message),
});
const privacySettings = createPrivacySettings({
    t,
    formatNumber: (value) => i18n.formatNumber(value),
    apiFetch,
    isAbortError,
    registerListbox: registerSettingsListbox,
    showBanner,
});

const login = createLoginController({
    overlayId: 'loginOverlay',
    tokenId: 'loginToken',
    inertSelector: '.settings-shell',
    onAuthenticated: () => bootstrapData(),
});

function showLogin() {
    login.show();
}

window.addEventListener(UNAUTHORIZED_EVENT, showLogin);

function applyLocalPreferences() {
    const appearance = appearanceSettings.apply();
    const motion = readPreference(preferenceKeys.motion, 'system') === 'reduced'
        ? 'reduced'
        : 'system';
    document.documentElement.dataset.motion = motion;
    document.getElementById('motionToggle').setAttribute(
        'aria-checked',
        motion === 'reduced' ? 'true' : 'false',
    );
    listboxes.get('languageSelect')?.setValue(i18n.getLocale());
    listboxes.get('settingsTimezoneSelect')?.setValue(
        readPreference(preferenceKeys.timezone, 'browser'),
    );
    return appearance;
}

function renderLocalizedState() {
    i18n.translate();
    listboxes.forEach((controller) => controller.refreshLabels());
    appearanceSettings.localize();
    connectionSettings.localize();
    privacySettings.localize();
}

async function submitLogin(token) {
    try {
        await login.submit(token);
    } catch (error) {
        if (!(error instanceof UnauthorizedError)) throw error;
        throw new Error('invalid token');
    }
}

function switchSettingsTab(name, { focus = true, updateHash = true } = {}) {
    const allowed = new Set(['source', 'privacy', 'preferences', 'about']);
    const nextName = allowed.has(name) ? name : 'source';
    document.querySelectorAll('#settingsTabBar [role="tab"]').forEach((button) => {
        const active = button.dataset.tab === nextName;
        button.setAttribute('aria-selected', active ? 'true' : 'false');
        button.tabIndex = active ? 0 : -1;
        if (active && focus) button.focus({ preventScroll: true });
    });
    document.querySelectorAll('[role="tabpanel"]').forEach((panel) => {
        panel.hidden = panel.id !== `tab-${nextName}`;
    });
    if (updateHash) window.history.replaceState(null, '', `#${nextName}`);
    if (nextName === 'source') connectionSettings.refreshStatus().catch(() => {});
}

function bindTabs() {
    const tabs = Array.from(document.querySelectorAll('#settingsTabBar [role="tab"]'));
    tabs.forEach((button) => {
        button.addEventListener('click', () => switchSettingsTab(button.dataset.tab));
        button.addEventListener('keydown', (event) => {
            const currentIndex = tabs.indexOf(event.currentTarget);
            let nextIndex = -1;
            if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
                nextIndex = (currentIndex + 1) % tabs.length;
            } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
                nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
            } else if (event.key === 'Home') {
                nextIndex = 0;
            } else if (event.key === 'End') {
                nextIndex = tabs.length - 1;
            }
            if (nextIndex >= 0) {
                event.preventDefault();
                switchSettingsTab(tabs[nextIndex].dataset.tab);
            }
        });
    });
}

function bindPreferenceControls() {
    appearanceSettings.mount();
    registerSettingsListbox('languageSelect', {
        value: i18n.getLocale(),
        options: SUPPORTED_LOCALES.map((locale) => ({
            value: locale.code,
            label: locale.native,
            subtitleKey: `localeName.${locale.code}`,
        })),
        onChange: (language) => {
            i18n.setLocale(language);
            renderLocalizedState();
        },
    });
    registerSettingsListbox('settingsTimezoneSelect', {
        value: readPreference(preferenceKeys.timezone, 'browser'),
        options: [
            { value: 'browser', labelKey: 'preferences.timezoneBrowser' },
            { value: 'UTC', labelKey: 'preferences.timezoneUtc' },
        ],
        onChange: (timezone) => writePreference(preferenceKeys.timezone, timezone),
    });

    document.getElementById('motionToggle').addEventListener('click', () => {
        const button = document.getElementById('motionToggle');
        const reduced = button.getAttribute('aria-checked') !== 'true';
        writePreference(preferenceKeys.motion, reduced ? 'reduced' : 'system');
        applyLocalPreferences();
    });
    document.getElementById('resetPreferencesBtn').addEventListener('click', () => {
        if (!window.confirm(t('preferences.resetConfirm'))) return;
        Object.values(preferenceKeys).forEach(removePreference);
        Object.values(APPEARANCE_PREFERENCE_KEYS).forEach(removePreference);
        i18n.setLocale('en', { persist: false });
        applyLocalPreferences();
        renderLocalizedState();
        showBanner('success', t('preferences.resetSuccess'));
    });
}

function bindAuthentication() {
    login.bind();
    document.getElementById('loginForm').addEventListener('submit', async (event) => {
        event.preventDefault();
        const tokenInput = document.getElementById('loginToken');
        try {
            await submitLogin(tokenInput.value);
            applyAppVersion();
            tokenInput.value = '';
        } catch (_error) {
            const error = document.getElementById('loginError');
            error.textContent = t('auth.invalid');
            error.hidden = false;
        }
    });
}

async function bootstrapData() {
    hideBanner();
    applyAppVersion();
    try {
        const statusResponse = await apiFetch('/api/auth/status');
        if (statusResponse.ok) {
            const status = await statusResponse.json();
            if (status.auth_required) {
                try {
                    await apiFetch('/api/privacy/settings');
                } catch (error) {
                    if (error instanceof UnauthorizedError) {
                        showLogin();
                        return;
                    }
                    throw error;
                }
            }
        }
        const results = await Promise.allSettled([
            privacySettings.load(),
            connectionSettings.load(),
        ]);
        if (results.some(
            (result) => result.status === 'rejected'
                && result.reason?.message !== 'unauthorized',
        )) {
            showBanner('error', t('error.settingsLoad'));
        }
    } catch (error) {
        if (error.message !== 'unauthorized') showBanner('error', t('error.settingsLoad'));
    }
}

function initialize() {
    i18n.translate();
    bindPreferenceControls();
    applyLocalPreferences();
    bindTabs();
    privacySettings.mount();
    connectionSettings.mount();
    bindAuthentication();
    const initialTab = window.location.hash.replace(/^#/, '');
    switchSettingsTab(initialTab, { focus: false, updateHash: false });
    renderLocalizedState();
    bootstrapData();
}

initialize();
