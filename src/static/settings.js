import { apiFetch, isAbortError, UnauthorizedError } from './js/http.js';
import { createLoginController } from './js/auth.js';
import { UNAUTHORIZED_EVENT } from './js/http.js';
import { readPreference, removePreference, writePreference } from './js/prefs.js';
import { createI18n } from './localization.js';
import { DEFAULT_THEME, THEMES, resolveTheme, themeScheme } from './js/themes.js';
import { SUPPORTED_LOCALES } from './js/locales.js';
import { applyAppVersion } from './js/app-info.js';
import { catalog, settingsMessages } from './js/messages-settings.js';

    const IMPORT_MAX_BYTES = 5 * 1024 * 1024;
    const preferenceKeys = Object.freeze({
        language: 'navidrome-language',
        theme: 'navidrome-theme',
        timezone: 'navidrome-timezone',
        motion: 'navidrome-motion',
    });

const messages = {
            'zh-CN': catalog(settingsMessages.zhCN),
            'zh-TW': catalog(settingsMessages.zhTW),
            en: catalog(settingsMessages.en),
            ja: catalog(settingsMessages.ja),
    };
    const i18n = createI18n({ messages, fallbackLocale: 'en' });
    const t = (key, values) => i18n.t(key, values);
    const state = {
        privacyStatus: 'loading',
        privacySettings: null,
        storageSnapshot: null,
        users: [],
        usersStatus: 'loading',
        servers: [],
        sourceReadiness: 'unknown',
        sourcePasswordConfigured: false,
        fallbackSourceConfig: null,
        sourceMessage: null,
    };
    const listboxes = new Map();
    let previewTimer = null;
    let retentionPreviewController = null;
    let userPreviewController = null;

    function isResponseOk(response) {
        return response && response.ok;
    }

    let lastUnauthorizedHandler = null;

    function onUnauthorized() {
        if (lastUnauthorizedHandler) lastUnauthorizedHandler();
    }

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

    function createListbox(rootId, {
        options = [],
        value = '',
        placeholderKey = 'common.none',
        onChange = () => {},
    } = {}) {
        const root = document.getElementById(rootId);
        const trigger = root.querySelector('[data-listbox-trigger]');
        const label = root.querySelector('[data-listbox-label]');
        const menu = root.querySelector('[role="listbox"]');
        let currentOptions = Array.from(options);
        let currentValue = value;
        let currentPlaceholderKey = placeholderKey;
        let disabled = false;

        function optionElements() {
            return Array.from(menu.querySelectorAll('[role="option"]'));
        }

        function close({ restoreFocus = false } = {}) {
            menu.hidden = true;
            root.dataset.open = 'false';
            trigger.setAttribute('aria-expanded', 'false');
            if (restoreFocus) trigger.focus();
        }

        function open(direction = 1) {
            if (disabled || currentOptions.length === 0) return;
            listboxes.forEach((controller) => {
                if (controller.root !== root) controller.close();
            });
            menu.hidden = false;
            root.dataset.open = 'true';
            trigger.setAttribute('aria-expanded', 'true');
            const elements = optionElements();
            const selectedIndex = currentOptions.findIndex((option) => String(option.value) === String(currentValue));
            const focusIndex = selectedIndex >= 0 ? selectedIndex : (direction < 0 ? elements.length - 1 : 0);
            elements[focusIndex]?.focus();
        }

        function updateTrigger() {
            const selected = currentOptions.find((option) => String(option.value) === String(currentValue));
            label.textContent = selected ? getOptionLabel(selected) : t(currentPlaceholderKey);
            label.dataset.placeholder = selected ? 'false' : 'true';
            root.dataset.value = selected ? String(selected.value) : '';
        }

        function renderOptions() {
            menu.replaceChildren();
            currentOptions.forEach((option) => {
                const item = document.createElement('button');
                item.type = 'button';
                item.role = 'option';
                item.className = 'settings-option';
                item.dataset.value = String(option.value);
                item.tabIndex = -1;
                if (option.subtitleKey) {
                    const lines = document.createElement('span');
                    lines.className = 'settings-option-lines';
                    const primary = document.createElement('span');
                    primary.className = 'settings-option-label';
                    primary.textContent = getOptionLabel(option);
                    const subtitle = document.createElement('span');
                    subtitle.className = 'settings-option-subtitle';
                    subtitle.textContent = t(option.subtitleKey);
                    lines.append(primary, subtitle);
                    item.appendChild(lines);
                } else {
                    item.textContent = getOptionLabel(option);
                }
                item.setAttribute('aria-selected', String(option.value) === String(currentValue) ? 'true' : 'false');
                item.addEventListener('click', () => {
                    setValue(option.value, { emit: true });
                    close({ restoreFocus: true });
                });
                menu.appendChild(item);
            });
            updateTrigger();
        }

        function setValue(nextValue, { emit = false } = {}) {
            const normalized = nextValue === null || nextValue === undefined ? '' : String(nextValue);
            const previous = currentValue;
            currentValue = normalized;
            optionElements().forEach((item) => {
                item.setAttribute('aria-selected', item.dataset.value === normalized ? 'true' : 'false');
            });
            updateTrigger();
            if (emit && normalized !== previous) onChange(normalized);
        }

        function setOptions(nextOptions, {
            preserveValue = true,
            selectFirst = false,
            placeholder = currentPlaceholderKey,
        } = {}) {
            currentOptions = Array.from(nextOptions || []);
            currentPlaceholderKey = placeholder;
            const exists = currentOptions.some((option) => String(option.value) === String(currentValue));
            if (!preserveValue || !exists) {
                currentValue = selectFirst && currentOptions.length > 0 ? String(currentOptions[0].value) : '';
            }
            renderOptions();
        }

        function setDisabled(nextDisabled) {
            disabled = Boolean(nextDisabled);
            trigger.disabled = disabled;
            root.dataset.disabled = disabled ? 'true' : 'false';
            if (disabled) close();
        }

        function refreshLabels() {
            renderOptions();
        }

        trigger.addEventListener('click', () => {
            if (menu.hidden) open();
            else close();
        });
        trigger.addEventListener('keydown', (event) => {
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                open(event.key === 'ArrowUp' ? -1 : 1);
            } else if (event.key === 'Escape') {
                close();
            }
        });
        menu.addEventListener('keydown', (event) => {
            const elements = optionElements();
            const currentIndex = elements.indexOf(document.activeElement);
            let nextIndex = -1;
            if (event.key === 'ArrowDown') nextIndex = (currentIndex + 1) % elements.length;
            else if (event.key === 'ArrowUp') nextIndex = (currentIndex - 1 + elements.length) % elements.length;
            else if (event.key === 'Home') nextIndex = 0;
            else if (event.key === 'End') nextIndex = elements.length - 1;
            else if (event.key === 'Escape') {
                event.preventDefault();
                close({ restoreFocus: true });
                return;
            } else if (event.key === 'Tab') {
                close();
                return;
            }
            if (nextIndex >= 0) {
                event.preventDefault();
                elements[nextIndex]?.focus();
            }
        });

        const controller = {
            close,
            getValue: () => currentValue,
            open,
            refreshLabels,
            root,
            setDisabled,
            setOptions,
            setValue,
        };
        listboxes.set(rootId, controller);
        renderOptions();
        return controller;
    }

    function applyLocalPreferences() {
        const theme = resolveTheme(readPreference(preferenceKeys.theme, DEFAULT_THEME));
        const motion = readPreference(preferenceKeys.motion, 'system') === 'reduced' ? 'reduced' : 'system';
        document.documentElement.dataset.theme = theme;
        document.documentElement.dataset.scheme = themeScheme(theme);
        document.documentElement.dataset.motion = motion;
        document.getElementById('motionToggle').setAttribute('aria-checked', motion === 'reduced' ? 'true' : 'false');
        listboxes.get('themeSelect')?.setValue(theme);
        listboxes.get('languageSelect')?.setValue(i18n.getLocale());
        listboxes.get('settingsTimezoneSelect')?.setValue(readPreference(preferenceKeys.timezone, 'browser'));
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

    function renderSourceReadiness() {
        const keyByState = {
            ok: 'source.statusOk',
            error: 'source.statusError',
            degraded: 'source.statusDegraded',
            unknown: 'source.statusUnknown',
        };
        const value = document.getElementById('sourceReadinessValue');
        value.textContent = t(keyByState[state.sourceReadiness] || keyByState.unknown);
        value.dataset.state = state.sourceReadiness;
        value.closest('.status-line').dataset.state = state.sourceReadiness;
    }

    function renderSourcePasswordPlaceholder() {
        const input = document.getElementById('sourcePass');
        input.placeholder = state.sourcePasswordConfigured
            ? t('source.passwordConfigured')
            : t('source.passwordPlaceholder');
    }

    function renderSourceFormState() {
        const editing = Boolean(document.getElementById('sourceForm').dataset.editingId);
        const password = document.getElementById('sourcePass');
        document.getElementById('saveSourceBtn').textContent = editing
            ? t('source.update')
            : t('source.save');
        document.getElementById('cancelSourceEditBtn').hidden = !editing;
        password.required = !editing;
        renderSourcePasswordPlaceholder();
    }

    function resetSourceForm() {
        const form = document.getElementById('sourceForm');
        form.reset();
        form.removeAttribute('data-editing-id');
        state.sourcePasswordConfigured = false;
        renderSourceFormState();
    }

    function renderFallbackSource() {
        const target = document.getElementById('sourceFallbackSummary');
        const fallback = state.fallbackSourceConfig;
        target.textContent = fallback?.url && fallback?.username && fallback?.password_configured
            ? t('source.fallbackConfigured', {
                username: fallback.username,
                url: fallback.url,
            })
            : t('source.fallbackMissing');
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
        renderPolicySummary();
        renderSourceReadiness();
        renderSourceFormState();
        renderFallbackSource();
        renderRetentionActions();
        updateStorageDisplay(state.storageSnapshot);
        updateRetentionPreviewText(state.storageSnapshot);
        renderUserOptions();
        renderServers();
        if (state.sourceMessage) {
            setSourceMessage(
                state.sourceMessage.key,
                state.sourceMessage.kind,
                state.sourceMessage.values,
            );
        }
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
        if (!isResponseOk(response)) throw new Error('preview failed');
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
            if (!isResponseOk(response)) throw new Error('privacy settings failed');
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
            if (!isResponseOk(response)) throw new Error('users failed');
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
        if (!isResponseOk(response)) throw new Error('user preview failed');
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

    function setSourceMessage(key, kind = 'info', values = {}) {
        state.sourceMessage = { key, kind, values };
        const element = document.getElementById('sourceMessage');
        element.dataset.kind = kind;
        element.textContent = t(key, values);
        element.hidden = false;
    }

    function clearSourceMessage() {
        state.sourceMessage = null;
        document.getElementById('sourceMessage').hidden = true;
    }

    function renderServers() {
        const list = document.getElementById('serverList');
        const servers = state.servers;
        list.replaceChildren();
        document.getElementById('serverEmpty').hidden = servers.length !== 0;
        servers.forEach((server) => {
            const row = document.createElement('div');
            row.className = 'server-row';
            const identity = document.createElement('div');
            identity.className = 'server-identity';
            const name = document.createElement('strong');
            name.textContent = server.display_name;
            const url = document.createElement('span');
            url.className = 'server-url';
            url.textContent = server.url;
            const statusBadge = document.createElement('span');
            statusBadge.className = 'server-status';
            statusBadge.dataset.enabled = String(Boolean(server.enabled));
            statusBadge.textContent = t(server.enabled ? 'source.enabledStatus' : 'source.disabledStatus');
            const detailLine = document.createElement('div');
            detailLine.className = 'server-detail-line';
            detailLine.append(url, statusBadge);
            identity.append(name, detailLine);

            const actions = document.createElement('div');
            actions.className = 'row-actions';
            const testButton = document.createElement('button');
            testButton.type = 'button';
            testButton.className = 'text-button';
            testButton.textContent = t('common.test');
            testButton.addEventListener('click', async () => {
                setSourceMessage('source.testing');
                try {
                    const testResponse = await apiFetch(`/api/servers/${encodeURIComponent(server.id)}/test`, {
                        method: 'POST',
                    });
                    if (!isResponseOk(testResponse)) throw new Error('server test failed');
                    const result = await testResponse.json();
                    setSourceMessage(result.ok ? 'source.testSuccess' : 'source.testFailure', result.ok ? 'success' : 'error');
                } catch (error) {
                    if (error.message !== 'unauthorized') setSourceMessage('source.testFailed', 'error');
                }
            });
            const editButton = document.createElement('button');
            editButton.type = 'button';
            editButton.className = 'text-button';
            editButton.textContent = t('common.edit');
            editButton.addEventListener('click', () => {
                document.getElementById('sourceName').value = server.display_name;
                document.getElementById('sourceUrl').value = server.url;
                document.getElementById('sourceUser').value = server.username;
                document.getElementById('sourcePass').value = '';
                document.getElementById('sourceEnabled').checked = Boolean(server.enabled);
                document.getElementById('sourceForm').dataset.editingId = server.id;
                state.sourcePasswordConfigured = Boolean(server.password_configured);
                renderSourceFormState();
                document.getElementById('sourceName').focus();
            });
            const deleteButton = document.createElement('button');
            deleteButton.type = 'button';
            deleteButton.className = 'text-button danger';
            deleteButton.textContent = t('common.delete');
            deleteButton.addEventListener('click', async () => {
                if (!window.confirm(t('source.deleteConfirm', { name: server.display_name }))) return;
                const deleteResponse = await apiFetch(`/api/servers/${encodeURIComponent(server.id)}`, {
                    method: 'DELETE',
                });
                if (!isResponseOk(deleteResponse)) {
                    setSourceMessage('source.saveFailed', 'error');
                    return;
                }
                if (document.getElementById('sourceForm').dataset.editingId === server.id) {
                    resetSourceForm();
                }
                await loadServers();
            });
            actions.append(testButton, editButton, deleteButton);
            row.append(identity, actions);
            list.appendChild(row);
        });
    }

    async function loadServers() {
        try {
            const response = await apiFetch('/api/servers');
            if (!isResponseOk(response)) throw new Error('servers failed');
            state.servers = await response.json();
            const editingId = document.getElementById('sourceForm').dataset.editingId;
            if (editingId && !state.servers.some((server) => server.id === editingId)) {
                resetSourceForm();
            }
            renderServers();
        } catch (error) {
            if (error.message !== 'unauthorized') setSourceMessage('source.loadFailed', 'error');
            throw error;
        }
    }

    async function loadSourceConfig() {
        try {
            const response = await apiFetch('/api/source/config');
            if (!isResponseOk(response)) throw new Error('source config failed');
            state.fallbackSourceConfig = await response.json();
            renderFallbackSource();
        } catch (error) {
            if (error.message !== 'unauthorized') setSourceMessage('source.configFailed', 'error');
            throw error;
        }
    }

    async function loadSourceReadiness() {
        try {
            const response = await apiFetch('/health/ready');
            if (!isResponseOk(response)) {
                state.sourceReadiness = 'degraded';
            } else {
                const data = await response.json();
                const upstream = data.checks && data.checks.upstream;
                if (upstream === 'ok') state.sourceReadiness = 'ok';
                else if (upstream === 'error') state.sourceReadiness = 'error';
                else if (data.status === 'degraded') state.sourceReadiness = 'degraded';
                else state.sourceReadiness = 'unknown';
            }
        } catch (_error) {
            state.sourceReadiness = 'unknown';
        }
        renderSourceReadiness();
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
        if (nextName === 'source') loadSourceReadiness().catch(() => {});
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
        createListbox('languageSelect', {
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
        createListbox('themeSelect', {
            value: readPreference(preferenceKeys.theme, DEFAULT_THEME),
            options: THEMES.map((theme) => ({
                value: theme.id,
                labelKey: `preferences.theme.${theme.id}`,
                subtitleKey: `common.scheme.${theme.scheme}`,
            })),
            onChange: (theme) => {
                writePreference(preferenceKeys.theme, theme);
                applyLocalPreferences();
            },
        });
        createListbox('settingsTimezoneSelect', {
            value: readPreference(preferenceKeys.timezone, 'browser'),
            options: [
                { value: 'browser', labelKey: 'preferences.timezoneBrowser' },
                { value: 'UTC', labelKey: 'preferences.timezoneUtc' },
            ],
            onChange: (timezone) => writePreference(preferenceKeys.timezone, timezone),
        });
        createListbox('userSelect', {
            placeholderKey: 'privacy.userLoading',
            onChange: () => refreshUserPreview().catch((error) => {
                if (!isAbortError(error)) showBanner('error', t('error.generic'));
            }),
        });

        document.addEventListener('click', (event) => {
            listboxes.forEach((controller) => {
                if (!controller.root.contains(event.target)) controller.close();
            });
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
                if (!isResponseOk(response)) throw new Error('save failed');
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
                if (!isResponseOk(response)) throw new Error('cleanup failed');
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
                if (!isResponseOk(response)) throw new Error('export failed');
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
                if (!isResponseOk(response)) throw new Error('import failed');
                const data = await response.json();
                showBanner('success', t('privacy.importSuccess', {
                    records: localizedCount(data.imported),
                    attempts: localizedCount(data.attempts_imported),
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
                if (!isResponseOk(response)) throw new Error('delete failed');
                const data = await response.json();
                showBanner('success', t('privacy.deleteSuccess', { count: localizedCount(data.deleted) }));
                await Promise.all([loadUsers(), refreshRetentionPreview()]);
            } catch (error) {
                if (error.message !== 'unauthorized') showBanner('error', t('privacy.deleteFailed'));
            }
        });
    }

    function bindSourceControls() {
        document.getElementById('refreshSourceStatus').addEventListener('click', () => {
            loadSourceReadiness().catch(() => {});
        });
        document.getElementById('cancelSourceEditBtn').addEventListener('click', () => {
            resetSourceForm();
            clearSourceMessage();
            document.getElementById('sourceName').focus();
        });
        document.getElementById('sourceForm').addEventListener('submit', async (event) => {
            event.preventDefault();
            const form = event.currentTarget;
            const saveButton = document.getElementById('saveSourceBtn');
            const displayName = document.getElementById('sourceName').value.trim();
            const url = document.getElementById('sourceUrl').value.trim();
            const username = document.getElementById('sourceUser').value.trim();
            const password = document.getElementById('sourcePass').value;
            const enabled = document.getElementById('sourceEnabled').checked;
            const editingId = form.dataset.editingId;
            if (!displayName) return setSourceMessage('source.nameRequired', 'error');
            if (!url) return setSourceMessage('source.urlRequired', 'error');
            if (!username) return setSourceMessage('source.userRequired', 'error');
            if (!editingId && !password) {
                return setSourceMessage('source.passwordRequired', 'error');
            }
            saveButton.disabled = true;
            try {
                const response = await apiFetch(
                    editingId ? `/api/servers/${encodeURIComponent(editingId)}` : '/api/servers',
                    {
                        method: editingId ? 'PUT' : 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            display_name: displayName,
                            url,
                            username,
                            password,
                            enabled,
                        }),
                    },
                );
                if (!isResponseOk(response)) throw new Error('save failed');
                resetSourceForm();
                await Promise.all([loadServers(), loadSourceReadiness()]);
                setSourceMessage('source.saved', 'success');
            } catch (error) {
                if (error.message !== 'unauthorized') setSourceMessage('source.saveFailed', 'error');
            } finally {
                saveButton.disabled = false;
            }
        });
        document.getElementById('testSourceBtn').addEventListener('click', async () => {
            const button = document.getElementById('testSourceBtn');
            const form = document.getElementById('sourceForm');
            setSourceMessage('source.testing');
            const displayName = document.getElementById('sourceName').value.trim();
            const url = document.getElementById('sourceUrl').value.trim();
            const username = document.getElementById('sourceUser').value.trim();
            const password = document.getElementById('sourcePass').value;
            const enabled = document.getElementById('sourceEnabled').checked;
            const editingId = form.dataset.editingId;
            if (!url) return setSourceMessage('source.urlRequired', 'error');
            if (!username) return setSourceMessage('source.userRequired', 'error');
            if (!editingId && !password) {
                return setSourceMessage('source.passwordRequired', 'error');
            }
            const payload = editingId
                ? {
                    display_name: displayName || 'Navidrome',
                    url,
                    username,
                    password,
                    enabled,
                }
                : { url, username, password };
            button.disabled = true;
            try {
                const endpoint = editingId
                    ? `/api/servers/${encodeURIComponent(editingId)}/test`
                    : '/api/source/test';
                const response = await apiFetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!isResponseOk(response)) throw new Error('test failed');
                const data = await response.json();
                setSourceMessage(data.ok ? 'source.testSuccess' : 'source.testFailure', data.ok ? 'success' : 'error');
            } catch (error) {
                if (error.message !== 'unauthorized') setSourceMessage('source.testFailed', 'error');
            } finally {
                button.disabled = false;
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
                loadSourceConfig(),
                loadServers(),
                loadSourceReadiness(),
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
        bindSourceControls();
        bindAuthentication();
        const initialTab = window.location.hash.replace(/^#/, '');
        switchSettingsTab(initialTab, { focus: false, updateHash: false });
        renderLocalizedState();
        bootstrapData();
    }

    initialize();
