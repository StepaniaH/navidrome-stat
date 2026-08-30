import { apiFetch, isAbortError, UnauthorizedError } from './js/http.js';
import { createLoginController } from './js/auth.js';
import { UNAUTHORIZED_EVENT } from './js/http.js';
import { readPreference, removePreference, writePreference } from './js/prefs.js';
import { createI18n } from './localization.js';
import { APPEARANCE_PREFERENCE_KEYS } from './js/themes.js';
import { createAppearanceSettings } from './js/settings/appearance-settings.js';
import { createConnectionSettings } from './js/settings/connection-settings.js';
import { SUPPORTED_LOCALES } from './js/locales.js';
import { applyAppVersion } from './js/app-info.js';
import { pageMessages } from './js/i18n/index.js';
import { createSelectListbox } from './js/listbox.js';

    const IMPORT_MAX_BYTES = 5 * 1024 * 1024;
    const preferenceKeys = Object.freeze({
        language: 'navidrome-language',
        timezone: 'navidrome-timezone',
        motion: 'navidrome-motion',
    });

const i18n = createI18n({ messages: pageMessages('settings'), fallbackLocale: 'en' });
    const t = (key, values) => i18n.t(key, values);
    const state = {
        privacyStatus: 'loading',
        privacySettings: null,
        storageSnapshot: null,
        users: [],
        usersStatus: 'loading',
    };
    const listboxes = new Map();
    let previewTimer = null;
    let retentionPreviewController = null;
    let userPreviewController = null;
    const appearanceSettings = createAppearanceSettings({
        t,
        confirmDiscard: (message) => window.confirm(message),
    });
    const connectionSettings = createConnectionSettings({
        t,
        apiFetch,
        confirmDelete: (message) => window.confirm(message),
    });

    const login = createLoginController({
        overlayId: 'loginOverlay',
        tokenId: 'loginToken',
        inertSelector: '.settings-shell',
        onAuthenticated: () => bootstrapData(),
    });

    window.addEventListener(UNAUTHORIZED_EVENT, () => showLogin());

    function showLogin() {
        login.show();
    }

    function showBanner(kind, message) {
        const banner = document.getElementById('settingsBanner');
        banner.dataset.kind = kind;
        banner.textContent = message;
        banner.hidden = false;
    }

    function hideBanner() {
        document.getElementById('settingsBanner').hidden = true;
    }

    function localizedCount(value) {
        return i18n.formatNumber(value);
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

    function applyLocalPreferences() {
        const appearance = appearanceSettings.apply();
        const motion = readPreference(preferenceKeys.motion, 'system') === 'reduced' ? 'reduced' : 'system';
        document.documentElement.dataset.motion = motion;
        document.getElementById('motionToggle').setAttribute('aria-checked', motion === 'reduced' ? 'true' : 'false');
        listboxes.get('languageSelect')?.setValue(i18n.getLocale());
        listboxes.get('settingsTimezoneSelect')?.setValue(readPreference(preferenceKeys.timezone, 'browser'));
        return appearance;
    }

    function formatBytes(bytes) {
        const value = Number(bytes) || 0;
        if (value < 1024) return `${value} B`;
        if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
        if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(2)} MB`;
        return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
    }

    function renderPolicySummary() {
        const summary = document.getElementById('policySummary');
        const retry = document.getElementById('policyRetry');
        summary.dataset.state = state.privacyStatus;
        summary.closest('.status-line').dataset.state = state.privacyStatus;
        retry.hidden = state.privacyStatus !== 'error';
        if (state.privacyStatus === 'loading') {
            summary.textContent = t('privacy.policyLoading');
            return;
        }
        if (state.privacyStatus === 'error') {
            summary.textContent = t('privacy.policyLoadError');
            return;
        }
        const persistedDays = state.privacySettings?.retention_days ?? null;
        summary.textContent = persistedDays === null
            ? t('privacy.summaryPermanent')
            : t('privacy.summaryFinite', { days: persistedDays });
    }

    function retentionDraftIsDirty() {
        if (state.privacyStatus !== 'ready' || !state.privacySettings) return false;
        const persisted = state.privacySettings.retention_days ?? null;
        return getRetentionDaysFromUi() !== persisted;
    }

    function renderRetentionActions() {
        const ready = state.privacyStatus === 'ready' && Boolean(state.privacySettings);
        const dirty = ready && retentionDraftIsDirty();
        const persistedFinite = ready && state.privacySettings.retention_days !== null;
        document.getElementById('saveRetentionBtn').disabled = !ready || !dirty;
        document.getElementById('applyRetentionBtn').disabled = !persistedFinite || dirty;
    }

    function updateStorageDisplay(preview) {
        if (!preview) {
            document.getElementById('storageEstimatedDetail').textContent = t('privacy.storagePending');
            return;
        }
        document.getElementById('storageCurrentSize').textContent = formatBytes(preview.database_bytes);
        document.getElementById('storageCurrentRecords').textContent = t('common.records', {
            count: localizedCount(preview.total_records),
        });

        if (document.getElementById('modePermanent').checked) {
            document.getElementById('storageEstimatedSize').textContent = formatBytes(preview.database_bytes);
            document.getElementById('storageEstimatedDetail').textContent = t('privacy.storagePermanent');
            return;
        }
        document.getElementById('storageEstimatedSize').textContent = formatBytes(preview.estimated_database_bytes_after);
        const released = Math.max(preview.database_bytes - preview.estimated_database_bytes_after, 0);
        document.getElementById('storageEstimatedDetail').textContent = t('privacy.storageRelease', {
            bytes: formatBytes(released),
            count: localizedCount(preview.records_to_delete),
        });
    }

    function updateRetentionPreviewText(preview) {
        const target = document.getElementById('retentionPreview');
        target.textContent = retentionPreviewText(preview);
    }

    function retentionPreviewText(preview) {
        if (!preview) {
            return t('privacy.storagePending');
        }
        if (preview.retention_days === null) {
            return t('privacy.previewPermanent');
        }
        const released = Math.max(preview.database_bytes - preview.estimated_database_bytes_after, 0);
        return t('privacy.previewFinite', {
            label: t('common.days', { count: preview.retention_days }),
            count: localizedCount(preview.records_to_delete),
            bytes: formatBytes(released),
        });
    }

    function renderUserOptions() {
        const controller = listboxes.get('userSelect');
        if (state.usersStatus === 'loading') {
            controller.setOptions([], { preserveValue: false, placeholder: 'privacy.userLoading' });
            controller.setDisabled(true);
            return;
        }
        const options = state.users.map((user) => ({
            value: user.username,
            label: () => t('privacy.userOption', {
                username: user.username,
                count: localizedCount(user.record_count),
            }),
        }));
        controller.setDisabled(options.length === 0);
        controller.setOptions(options, {
            preserveValue: true,
            selectFirst: true,
            placeholder: 'privacy.noUsers',
        });
    }

    function renderLocalizedState() {
        i18n.translate();
        listboxes.forEach((controller) => controller.refreshLabels());
        appearanceSettings.localize();
        connectionSettings.localize();
        renderPolicySummary();
        renderRetentionActions();
        updateStorageDisplay(state.storageSnapshot);
        updateRetentionPreviewText(state.storageSnapshot);
        renderUserOptions();
        refreshUserPreview().catch(() => {});
    }

    function updateRetentionModeVisuals() {
        document.querySelectorAll('.retention-choice').forEach((choice) => {
            const radio = choice.querySelector('input[type="radio"]');
            choice.dataset.selected = radio && radio.checked ? 'true' : 'false';
        });
    }

    function getRetentionDaysFromUi() {
        if (document.getElementById('modePermanent').checked) return null;
        return Number(document.getElementById('retentionSlider').value);
    }

    function applyRetentionUi(permanent, days) {
        document.getElementById('modePermanent').checked = Boolean(permanent);
        document.getElementById('modeFinite').checked = !permanent;
        const effectiveDays = Number(days) || 90;
        document.getElementById('retentionSlider').value = String(effectiveDays);
        document.getElementById('retentionValue').textContent = t('common.days', { count: effectiveDays });
        document.getElementById('retentionSliderWrap').hidden = Boolean(permanent);
        updateRetentionModeVisuals();
        renderPolicySummary();
        renderRetentionActions();
    }

    async function refreshRetentionPreview(days = getRetentionDaysFromUi()) {
        if (retentionPreviewController) retentionPreviewController.abort();
        const controller = new AbortController();
        retentionPreviewController = controller;
        const endpoint = days === null
            ? '/api/privacy/storage'
            : `/api/privacy/retention/preview?days=${encodeURIComponent(days)}`;
        const response = await apiFetch(endpoint, {
            signal: controller.signal,
        });
        if (!response.ok) throw new Error('preview failed');
        const payload = await response.json();
        const data = days === null
            ? {
                ...payload,
                retention_days: null,
                records_to_delete: 0,
                history_records_to_delete: 0,
                attempt_records_to_delete: 0,
                bytes_to_delete: 0,
                estimated_database_bytes_after: payload.database_bytes,
            }
            : payload;
        if (retentionPreviewController !== controller) return null;
        state.storageSnapshot = data;
        updateStorageDisplay(data);
        updateRetentionPreviewText(data);
        retentionPreviewController = null;
        return data;
    }

    function scheduleRetentionPreview() {
        if (previewTimer) window.clearTimeout(previewTimer);
        previewTimer = window.setTimeout(() => {
            refreshRetentionPreview().catch((error) => {
                if (!isAbortError(error)) showBanner('error', t('error.generic'));
            });
        }, 160);
    }

    async function loadPrivacySettings() {
        state.privacyStatus = 'loading';
        renderPolicySummary();
        try {
            const response = await apiFetch('/api/privacy/settings');
            if (!response.ok) throw new Error('privacy settings failed');
            const data = await response.json();
            state.privacySettings = data;
            state.privacyStatus = 'ready';
            applyRetentionUi(Boolean(data.permanent), data.retention_days);
            try {
                await refreshRetentionPreview();
            } catch (previewError) {
                if (previewError.message === 'unauthorized') throw previewError;
                if (isAbortError(previewError)) return;
                state.storageSnapshot = null;
                updateStorageDisplay(null);
                updateRetentionPreviewText(null);
            }
        } catch (error) {
            if (error.message === 'unauthorized') throw error;
            state.privacyStatus = 'error';
            renderPolicySummary();
            renderRetentionActions();
            throw error;
        }
    }

    async function loadUsers() {
        state.usersStatus = 'loading';
        renderUserOptions();
        try {
            const response = await apiFetch('/api/privacy/users');
            if (!response.ok) throw new Error('users failed');
            state.users = await response.json();
            state.usersStatus = 'ready';
            renderUserOptions();
            await refreshUserPreview();
        } catch (error) {
            if (isAbortError(error)) return;
            if (error.message === 'unauthorized') throw error;
            state.users = [];
            state.usersStatus = 'error';
            renderUserOptions();
            throw error;
        }
    }

    async function refreshUserPreview() {
        const username = listboxes.get('userSelect')?.getValue();
        const preview = document.getElementById('userPreview');
        if (userPreviewController) userPreviewController.abort();
        if (!username) {
            preview.textContent = t('privacy.userPreview', { count: 0 });
            userPreviewController = null;
            return null;
        }
        const controller = new AbortController();
        userPreviewController = controller;
        const response = await apiFetch(
            `/api/privacy/users/${encodeURIComponent(username)}/delete/preview`,
            { signal: controller.signal },
        );
        if (!response.ok) throw new Error('user preview failed');
        const data = await response.json();
        if (
            userPreviewController !== controller
            || listboxes.get('userSelect')?.getValue() !== username
        ) return null;
        const text = t('privacy.userPreview', {
            count: localizedCount(data.records_to_delete),
        });
        preview.textContent = text;
        userPreviewController = null;
        return { username, count: data.records_to_delete, text };
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
                if (event.key === 'ArrowRight' || event.key === 'ArrowDown') nextIndex = (currentIndex + 1) % tabs.length;
                else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
                else if (event.key === 'Home') nextIndex = 0;
                else if (event.key === 'End') nextIndex = tabs.length - 1;
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
        registerSettingsListbox('userSelect', {
            placeholderKey: 'privacy.userLoading',
            onChange: () => refreshUserPreview().catch((error) => {
                if (!isAbortError(error)) showBanner('error', t('error.generic'));
            }),
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

    function bindPrivacyControls() {
        document.getElementById('policyRetry').addEventListener('click', () => {
            loadPrivacySettings().catch(() => {
                showBanner('error', t('error.settingsLoad'));
            });
        });
        document.querySelectorAll('input[name="retentionMode"]').forEach((radio) => {
            radio.addEventListener('change', () => {
                updateRetentionModeVisuals();
                const permanent = document.getElementById('modePermanent').checked;
                document.getElementById('retentionSliderWrap').hidden = permanent;
                renderPolicySummary();
                renderRetentionActions();
                refreshRetentionPreview().catch((error) => {
                    if (!isAbortError(error)) showBanner('error', t('error.generic'));
                });
            });
        });
        document.getElementById('retentionSlider').addEventListener('input', (event) => {
            document.getElementById('retentionValue').textContent = t('common.days', {
                count: event.target.value,
            });
            renderPolicySummary();
            renderRetentionActions();
            scheduleRetentionPreview();
        });
        document.getElementById('saveRetentionBtn').addEventListener('click', async () => {
            const button = document.getElementById('saveRetentionBtn');
            const draftDays = getRetentionDaysFromUi();
            if (previewTimer) window.clearTimeout(previewTimer);
            previewTimer = null;
            button.disabled = true;
            try {
                const preview = await refreshRetentionPreview(draftDays);
                if (!preview) return;
                if (
                    draftDays !== null
                    && !window.confirm(t('privacy.retentionSaveConfirm', {
                        preview: retentionPreviewText(preview),
                    }))
                ) return;
                const response = await apiFetch('/api/privacy/settings', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ retention_days: draftDays }),
                });
                if (!response.ok) throw new Error('save failed');
                state.privacySettings = await response.json();
                state.privacyStatus = 'ready';
                renderPolicySummary();
                renderRetentionActions();
                showBanner('success', t('privacy.retentionSaved'));
                await refreshRetentionPreview(state.privacySettings.retention_days ?? null);
            } catch (error) {
                if (error.message !== 'unauthorized' && !isAbortError(error)) {
                    showBanner('error', t('error.generic'));
                }
            } finally {
                renderRetentionActions();
            }
        });
        document.getElementById('applyRetentionBtn').addEventListener('click', async () => {
            const button = document.getElementById('applyRetentionBtn');
            const persistedDays = state.privacySettings?.retention_days ?? null;
            if (previewTimer) window.clearTimeout(previewTimer);
            previewTimer = null;
            if (retentionDraftIsDirty()) {
                showBanner('error', t('privacy.saveFirst'));
                return;
            }
            if (persistedDays === null) {
                showBanner('error', t('privacy.noCleanup'));
                return;
            }
            button.disabled = true;
            try {
                const preview = await refreshRetentionPreview(persistedDays);
                if (!preview) return;
                if (!window.confirm(t('privacy.cleanupConfirm', {
                    preview: retentionPreviewText(preview),
                }))) return;
                const response = await apiFetch('/api/privacy/retention/apply', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        confirm: true,
                        expected_retention_days: persistedDays,
                    }),
                });
                if (response.status === 409) {
                    await loadPrivacySettings();
                    showBanner('error', t('privacy.policyChanged'));
                    return;
                }
                if (!response.ok) throw new Error('cleanup failed');
                const data = await response.json();
                showBanner('success', t('privacy.cleanupSuccess', { count: localizedCount(data.deleted) }));
                await Promise.all([loadUsers(), refreshRetentionPreview(persistedDays)]);
            } catch (error) {
                if (error.message !== 'unauthorized' && !isAbortError(error)) {
                    showBanner('error', t('privacy.cleanupFailed'));
                }
            } finally {
                renderRetentionActions();
            }
        });
        document.getElementById('exportBtn').addEventListener('click', async () => {
            const username = listboxes.get('userSelect').getValue();
            if (!username) {
                showBanner('error', t('privacy.selectUserFirst'));
                return;
            }
            try {
                const response = await apiFetch(`/api/privacy/users/${encodeURIComponent(username)}/export`);
                if (!response.ok) throw new Error('export failed');
                const blob = await response.blob();
                const objectUrl = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = objectUrl;
                link.download = 'navidrome-stat-export.json';
                link.click();
                window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
                showBanner('success', t('privacy.exportSuccess', { username }));
            } catch (error) {
                if (error.message !== 'unauthorized') showBanner('error', t('privacy.exportFailed'));
            }
        });
        document.getElementById('importBtn').addEventListener('click', () => {
            document.getElementById('importFile').click();
        });
        document.getElementById('importFile').addEventListener('change', async (event) => {
            const username = listboxes.get('userSelect').getValue();
            const file = event.target.files[0];
            event.target.value = '';
            if (!username || !file) return;
            if (file.size > IMPORT_MAX_BYTES) {
                showBanner('error', t('privacy.importTooLarge'));
                return;
            }
            try {
                const payload = JSON.parse(await file.text());
                const records = Array.isArray(payload.records) ? payload.records.length : 0;
                const attempts = Array.isArray(payload.attempts) ? payload.attempts.length : 0;
                if (!window.confirm(t('privacy.importConfirm', {
                    username,
                    records: localizedCount(records),
                    attempts: localizedCount(attempts),
                }))) return;
                const response = await apiFetch(`/api/privacy/users/${encodeURIComponent(username)}/import`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        payload,
                        merge: document.getElementById('mergeImport').checked,
                    }),
                });
                if (!response.ok) throw new Error('import failed');
                const data = await response.json();
                showBanner('success', t('privacy.importSuccess', {
                    records: localizedCount(data.imported),
                    attempts: localizedCount(data.attempts_imported),
                    skipped: localizedCount(data.skipped),
                    conflicts: localizedCount(data.conflicts),
                }));
                await Promise.all([loadUsers(), refreshRetentionPreview()]);
            } catch (error) {
                if (error.message !== 'unauthorized') showBanner('error', t('privacy.importFailed'));
            }
        });
        document.getElementById('deleteUserBtn').addEventListener('click', async () => {
            const username = listboxes.get('userSelect').getValue();
            if (!username) {
                showBanner('error', t('privacy.selectUserFirst'));
                return;
            }
            try {
                const preview = await refreshUserPreview();
                if (!preview || preview.username !== username) return;
                if (!window.confirm(t('privacy.deleteConfirm', {
                    preview: preview.text,
                    username,
                }))) return;
                const response = await apiFetch(`/api/privacy/users/${encodeURIComponent(username)}/delete`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ confirm: true }),
                });
                if (!response.ok) throw new Error('delete failed');
                const data = await response.json();
                showBanner('success', t('privacy.deleteSuccess', { count: localizedCount(data.deleted) }));
                await Promise.all([loadUsers(), refreshRetentionPreview()]);
            } catch (error) {
                if (error.message !== 'unauthorized') showBanner('error', t('privacy.deleteFailed'));
            }
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
                loadPrivacySettings(),
                loadUsers(),
                connectionSettings.load(),
            ]);
            if (results.some((result) => result.status === 'rejected' && result.reason?.message !== 'unauthorized')) {
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
        bindPrivacyControls();
        connectionSettings.mount();
        bindAuthentication();
        const initialTab = window.location.hash.replace(/^#/, '');
        switchSettingsTab(initialTab, { focus: false, updateHash: false });
        renderLocalizedState();
        bootstrapData();
    }

    initialize();
