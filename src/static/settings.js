(function initSettingsPage() {
    'use strict';

    const { createI18n, readPreference, removePreference, writePreference } = window.NavidromeI18n;
    const fetchOptions = { credentials: 'same-origin' };
    const preferenceKeys = Object.freeze({
        language: 'navidrome-language',
        theme: 'navidrome-theme',
        timezone: 'navidrome-timezone',
        motion: 'navidrome-motion',
    });

    const messages = {
        'zh-CN': {
            'page.title': '设置 · Navidrome Statistics',
            'page.heading': '设置',
            'page.description': '管理连接、数据边界与本地显示偏好。',
            'nav.back': '返回统计',
            'nav.categories': '设置分类',
            'nav.group.data': '服务与数据',
            'nav.group.app': '应用',
            'nav.group.project': '项目',
            'tab.source': '连接',
            'tab.privacy': '隐私',
            'tab.preferences': '偏好',
            'tab.about': '关于',
            'common.loading': '加载中…',
            'common.retry': '重试',
            'common.refresh': '刷新',
            'common.none': '暂无数据',
            'common.records': '{count} 条记录',
            'common.days': '{count} 天',
            'common.permanent': '永久保留',
            'common.edit': '编辑',
            'common.delete': '删除',
            'common.test': '测试',
            'common.cancel': '取消',
            'auth.heading': '需要访问令牌',
            'auth.description': '输入部署方提供的统计服务访问令牌。',
            'auth.token': '访问令牌',
            'auth.login': '登录',
            'auth.invalid': '令牌无效，请重试。',
            'source.heading': 'Navidrome 连接',
            'source.description': '管理统计服务读取播放状态所使用的服务器。连接更改保存后立即应用。',
            'source.status': '上游状态',
            'source.statusUnknown': '尚未检查',
            'source.statusOk': '连接正常',
            'source.statusError': '连接异常',
            'source.statusDegraded': '部分功能不可用',
            'source.savedConnections': '已保存的服务器',
            'source.savedConnectionsHelp': '密码不会在页面或 API 响应中回显。',
            'source.noServers': '尚未保存服务器。',
            'source.formHeading': '连接详情',
            'source.formDescription': '编辑现有服务器，或填写下方信息新增连接。',
            'source.serverName': '显示名称',
            'source.namePlaceholder': '例如：家庭 Navidrome',
            'source.url': 'Navidrome URL',
            'source.username': '用户名',
            'source.usernamePlaceholder': '账户名',
            'source.password': '密码',
            'source.passwordPlaceholder': '留空则保持不变',
            'source.passwordConfigured': '已配置 · 留空则保持不变',
            'source.save': '保存连接',
            'source.update': '更新连接',
            'source.testConnection': '测试当前表单',
            'source.testing': '正在测试连接…',
            'source.testSuccess': '连接成功。',
            'source.testFailure': '连接失败，请核对地址与凭据。',
            'source.testFailed': '无法完成连接测试。',
            'source.saved': '连接已保存并立即应用。',
            'source.loadFailed': '无法加载服务器列表。',
            'source.configFailed': '无法加载连接配置。',
            'source.saveFailed': '保存失败。',
            'source.nameRequired': '请填写服务器显示名称。',
            'source.urlRequired': '请填写 Navidrome URL。',
            'source.userRequired': '请填写用户名。',
            'source.deleteConfirm': '删除服务器“{name}”？这不会删除已有播放统计。',
            'source.envTitle': '环境变量优先级',
            'source.envDescription': 'NAVIDROME_URL、NAVIDROME_USER 与 NAVIDROME_PASS 始终优先于页面保存的兼容连接配置。',
            'privacy.heading': '隐私与数据',
            'privacy.description': '控制行为数据的保留期限，并按用户导出或删除记录。',
            'privacy.currentPolicy': '当前保留策略',
            'privacy.policyLoading': '正在读取当前策略…',
            'privacy.policyLoadError': '未能读取策略。现有数据未被修改。',
            'privacy.retention': '数据保留',
            'privacy.retentionDescription': '先保存策略；只有点击“确认清理”才会删除超期记录。',
            'privacy.retentionMode': '保留方式',
            'privacy.finiteRetention': '指定天数',
            'privacy.finiteHelp': '1–360 天',
            'privacy.summaryPermanent': '永久保留，除非你主动删除。',
            'privacy.summaryFinite': '保留最近 {days} 天，超期记录仅在确认后清理。',
            'privacy.previewPermanent': '当前策略不会自动删除播放记录。',
            'privacy.previewFinite': '按 {label} 计算：将影响 {count} 条记录，预计释放 {bytes}。',
            'privacy.saveRetention': '保存策略',
            'privacy.cleanup': '确认清理',
            'privacy.retentionSaved': '保留策略已保存。',
            'privacy.noCleanup': '当前为永久保留，无需清理。',
            'privacy.cleanupConfirm': '此操作不可撤销。\n\n{preview}\n\n确定删除这些超期记录吗？',
            'privacy.cleanupSuccess': '已清理 {count} 条超期记录。',
            'privacy.cleanupFailed': '清理失败，请重试。',
            'privacy.storage': '数据占用',
            'privacy.storageDescription': '以下估算只基于统计数据库，不读取媒体文件。',
            'privacy.currentDatabaseSize': '当前数据库',
            'privacy.estimatedStorage': '按当前策略预计',
            'privacy.storagePermanent': '永久保留，预计占用不变',
            'privacy.storageRelease': '预计释放 {bytes} · {count} 条',
            'privacy.storagePending': '策略加载后显示估算',
            'privacy.userData': '按用户管理',
            'privacy.userDataDescription': '导出、导入与删除都只作用于当前选择的用户。',
            'privacy.selectUser': '用户',
            'privacy.userLoading': '正在读取用户…',
            'privacy.noUsers': '暂无用户数据',
            'privacy.userOption': '{username} · {count} 条',
            'privacy.userPreview': '删除预览：{count} 条记录',
            'privacy.export': '导出 JSON',
            'privacy.import': '导入 JSON',
            'privacy.mergeImport': '合并导入',
            'privacy.mergeImportHelp': '关闭后会先清空该用户的既有数据。',
            'privacy.deleteUser': '删除该用户数据',
            'privacy.exportSuccess': '已导出用户“{username}”的数据。',
            'privacy.exportFailed': '导出失败。',
            'privacy.importConfirm': '为“{username}”导入 {count} 条记录？',
            'privacy.importSuccess': '已导入 {count} 条记录。',
            'privacy.importFailed': '导入失败，请检查 JSON 格式与用户名。',
            'privacy.deleteConfirm': '此操作不可撤销。\n\n{preview}\n\n确定删除用户“{username}”的全部播放数据吗？',
            'privacy.deleteSuccess': '已删除 {count} 条记录。',
            'privacy.deleteFailed': '删除失败。',
            'privacy.selectUserFirst': '请先选择用户。',
            'privacy.principles': '数据边界',
            'privacy.principleRetention': '播放历史、用户名、曲目、艺人、专辑与客户端名称均属于个人行为数据。',
            'privacy.principleCleanup': '清理和删除前会提供影响预览，并要求再次确认。',
            'privacy.principleExport': '导出仅包含所选用户的数据，服务不会记录导出内容。',
            'privacy.principleNotice': '部署方仍需确认访问边界、告知方式、备份位置与实际保留周期。',
            'preferences.heading': '偏好',
            'preferences.description': '这些选项只保存在当前浏览器，不会上传到服务器。',
            'preferences.language': '界面语言',
            'preferences.languageHelp': '切换后立即更新设置页与统计页。',
            'preferences.timezone': '统计时区',
            'preferences.timezoneHelp': '“浏览器时区”会使用当前设备报告的 IANA 时区。',
            'preferences.timezoneBrowser': '浏览器时区',
            'preferences.timezoneUtc': 'UTC',
            'preferences.theme': '主题',
            'preferences.themeHelp': '选择适合当前环境的深色或浅色配色。',
            'preferences.themeFrappe': 'Frappe · 深色',
            'preferences.themeLatte': 'Latte · 浅色',
            'preferences.motion': '减少动态效果',
            'preferences.motionHelp': '关闭脉冲、过渡和骨架动画，适合晕动敏感或低性能设备。',
            'preferences.reset': '恢复本地偏好',
            'preferences.resetHelp': '恢复英语、Frappe、浏览器时区和系统默认动效。',
            'preferences.resetButton': '恢复默认值',
            'preferences.resetConfirm': '恢复当前浏览器中的所有显示偏好？',
            'preferences.resetSuccess': '本地显示偏好已恢复默认值。',
            'about.heading': '关于',
            'about.description': 'Navidrome Statistic 是一个自托管的播放状态与收听习惯分析工具。',
            'about.project': '项目',
            'about.runtime': '运行方式',
            'about.runtimeValue': '自托管 · 本地 SQLite',
            'about.license': '许可证',
            'about.repository': '源代码',
            'about.repositoryValue': 'GitHub 仓库',
            'about.privacy': '隐私说明',
            'about.privacyValue': '查看项目隐私文档',
            'error.generic': '操作失败，请重试。',
            'error.settingsLoad': '部分设置未能加载；未完成的项目已标出。',
        },
        en: {
            'page.title': 'Settings · Navidrome Statistics',
            'page.heading': 'Settings',
            'page.description': 'Manage connections, data boundaries, and local display preferences.',
            'nav.back': 'Back to statistics',
            'nav.categories': 'Settings categories',
            'nav.group.data': 'Service & data',
            'nav.group.app': 'Application',
            'nav.group.project': 'Project',
            'tab.source': 'Connections',
            'tab.privacy': 'Privacy',
            'tab.preferences': 'Preferences',
            'tab.about': 'About',
            'common.loading': 'Loading…',
            'common.retry': 'Retry',
            'common.refresh': 'Refresh',
            'common.none': 'No data',
            'common.records': '{count} records',
            'common.days': '{count} days',
            'common.permanent': 'Keep forever',
            'common.edit': 'Edit',
            'common.delete': 'Delete',
            'common.test': 'Test',
            'common.cancel': 'Cancel',
            'auth.heading': 'Access token required',
            'auth.description': 'Enter the statistics service token provided by the operator.',
            'auth.token': 'Access token',
            'auth.login': 'Log in',
            'auth.invalid': 'That token is not valid. Try again.',
            'source.heading': 'Navidrome connections',
            'source.description': 'Manage the servers used to read playback state. Saved changes apply immediately.',
            'source.status': 'Upstream status',
            'source.statusUnknown': 'Not checked yet',
            'source.statusOk': 'Connected',
            'source.statusError': 'Connection issue',
            'source.statusDegraded': 'Some features unavailable',
            'source.savedConnections': 'Saved servers',
            'source.savedConnectionsHelp': 'Passwords are never returned to this page or exposed by the API.',
            'source.noServers': 'No servers have been saved.',
            'source.formHeading': 'Connection details',
            'source.formDescription': 'Edit a saved server or fill in the fields below to add one.',
            'source.serverName': 'Display name',
            'source.namePlaceholder': 'e.g. Home Navidrome',
            'source.url': 'Navidrome URL',
            'source.username': 'Username',
            'source.usernamePlaceholder': 'Account name',
            'source.password': 'Password',
            'source.passwordPlaceholder': 'Leave blank to keep current',
            'source.passwordConfigured': 'Configured · leave blank to keep current',
            'source.save': 'Save connection',
            'source.update': 'Update connection',
            'source.testConnection': 'Test current form',
            'source.testing': 'Testing connection…',
            'source.testSuccess': 'Connection succeeded.',
            'source.testFailure': 'Connection failed. Check the URL and credentials.',
            'source.testFailed': 'The connection test could not be completed.',
            'source.saved': 'Connection saved and applied immediately.',
            'source.loadFailed': 'Unable to load the server list.',
            'source.configFailed': 'Unable to load the connection configuration.',
            'source.saveFailed': 'Save failed.',
            'source.nameRequired': 'Enter a server display name.',
            'source.urlRequired': 'Enter the Navidrome URL.',
            'source.userRequired': 'Enter a username.',
            'source.deleteConfirm': 'Delete “{name}”? Existing playback statistics will be kept.',
            'source.envTitle': 'Environment variable precedence',
            'source.envDescription': 'NAVIDROME_URL, NAVIDROME_USER, and NAVIDROME_PASS always take precedence over the compatible connection saved here.',
            'privacy.heading': 'Privacy & data',
            'privacy.description': 'Control how long behavioral data is kept, then export or delete records by user.',
            'privacy.currentPolicy': 'Current retention policy',
            'privacy.policyLoading': 'Reading the current policy…',
            'privacy.policyLoadError': 'The policy could not be loaded. Existing data was not changed.',
            'privacy.retention': 'Data retention',
            'privacy.retentionDescription': 'Save the policy first. Records are deleted only after you select “Confirm cleanup.”',
            'privacy.retentionMode': 'Retention mode',
            'privacy.finiteRetention': 'Keep for a period',
            'privacy.finiteHelp': '1–360 days',
            'privacy.summaryPermanent': 'Kept forever unless you explicitly delete it.',
            'privacy.summaryFinite': 'Keep the most recent {days} days. Older records are removed only after confirmation.',
            'privacy.previewPermanent': 'The current policy does not automatically delete playback records.',
            'privacy.previewFinite': 'For {label}: {count} records affected, approximately {bytes} released.',
            'privacy.saveRetention': 'Save policy',
            'privacy.cleanup': 'Confirm cleanup',
            'privacy.retentionSaved': 'Retention policy saved.',
            'privacy.noCleanup': 'Retention is permanent; no cleanup is needed.',
            'privacy.cleanupConfirm': 'This action cannot be undone.\n\n{preview}\n\nDelete these expired records?',
            'privacy.cleanupSuccess': 'Deleted {count} expired records.',
            'privacy.cleanupFailed': 'Cleanup failed. Please try again.',
            'privacy.storage': 'Data footprint',
            'privacy.storageDescription': 'These estimates cover the statistics database only, never media files.',
            'privacy.currentDatabaseSize': 'Current database',
            'privacy.estimatedStorage': 'Estimated with this policy',
            'privacy.storagePermanent': 'Permanent retention; estimated size is unchanged',
            'privacy.storageRelease': 'About {bytes} released · {count} records',
            'privacy.storagePending': 'Estimate appears after the policy loads',
            'privacy.userData': 'Manage by user',
            'privacy.userDataDescription': 'Export, import, and delete actions affect only the selected user.',
            'privacy.selectUser': 'User',
            'privacy.userLoading': 'Reading users…',
            'privacy.noUsers': 'No user data',
            'privacy.userOption': '{username} · {count} records',
            'privacy.userPreview': 'Delete preview: {count} records',
            'privacy.export': 'Export JSON',
            'privacy.import': 'Import JSON',
            'privacy.mergeImport': 'Merge import',
            'privacy.mergeImportHelp': 'When off, existing data for this user is cleared first.',
            'privacy.deleteUser': 'Delete this user’s data',
            'privacy.exportSuccess': 'Exported data for “{username}”.',
            'privacy.exportFailed': 'Export failed.',
            'privacy.importConfirm': 'Import {count} records for “{username}”?',
            'privacy.importSuccess': 'Imported {count} records.',
            'privacy.importFailed': 'Import failed. Check the JSON format and username.',
            'privacy.deleteConfirm': 'This action cannot be undone.\n\n{preview}\n\nDelete all playback data for “{username}”?',
            'privacy.deleteSuccess': 'Deleted {count} records.',
            'privacy.deleteFailed': 'Delete failed.',
            'privacy.selectUserFirst': 'Select a user first.',
            'privacy.principles': 'Data boundaries',
            'privacy.principleRetention': 'Playback history, usernames, tracks, artists, albums, and client names are all behavioral data.',
            'privacy.principleCleanup': 'Cleanup and deletion show an impact preview and require another confirmation.',
            'privacy.principleExport': 'Exports contain data for the selected user only; export contents are not logged.',
            'privacy.principleNotice': 'The operator must still confirm access boundaries, notice, backup locations, and the actual retention period.',
            'preferences.heading': 'Preferences',
            'preferences.description': 'These options stay in this browser and are never uploaded to the server.',
            'preferences.language': 'Interface language',
            'preferences.languageHelp': 'Changes the settings and statistics pages immediately.',
            'preferences.timezone': 'Statistics timezone',
            'preferences.timezoneHelp': '“Browser timezone” uses the IANA timezone reported by this device.',
            'preferences.timezoneBrowser': 'Browser timezone',
            'preferences.timezoneUtc': 'UTC',
            'preferences.theme': 'Theme',
            'preferences.themeHelp': 'Choose a dark or light palette for the current environment.',
            'preferences.themeFrappe': 'Frappe · Dark',
            'preferences.themeLatte': 'Latte · Light',
            'preferences.motion': 'Reduce motion',
            'preferences.motionHelp': 'Disables pulses, transitions, and skeleton animation for motion sensitivity or slower devices.',
            'preferences.reset': 'Reset local preferences',
            'preferences.resetHelp': 'Restores English, Frappe, browser timezone, and system motion defaults.',
            'preferences.resetButton': 'Restore defaults',
            'preferences.resetConfirm': 'Restore all display preferences in this browser?',
            'preferences.resetSuccess': 'Local display preferences restored to defaults.',
            'about.heading': 'About',
            'about.description': 'Navidrome Statistic is a self-hosted playback status and listening-habits tool.',
            'about.project': 'Project',
            'about.runtime': 'Runtime',
            'about.runtimeValue': 'Self-hosted · local SQLite',
            'about.license': 'License',
            'about.repository': 'Source',
            'about.repositoryValue': 'GitHub repository',
            'about.privacy': 'Privacy',
            'about.privacyValue': 'Read the project privacy guide',
            'error.generic': 'The operation failed. Please try again.',
            'error.settingsLoad': 'Some settings could not be loaded; affected sections are marked.',
        },
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
        sourceMessage: null,
    };
    const listboxes = new Map();
    let previewTimer = null;

    function isResponseOk(response) {
        return response && response.ok;
    }

    async function apiFetch(url, options = {}) {
        const response = await fetch(url, { ...fetchOptions, ...options });
        if (response.status === 401) {
            showLogin();
            throw new Error('unauthorized');
        }
        return response;
    }

    function showLogin() {
        document.getElementById('loginOverlay').hidden = false;
    }

    function hideLogin() {
        document.getElementById('loginOverlay').hidden = true;
        document.getElementById('loginError').hidden = true;
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
                item.textContent = getOptionLabel(option);
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
        const theme = ['frappe', 'latte'].includes(readPreference(preferenceKeys.theme, 'frappe'))
            ? readPreference(preferenceKeys.theme, 'frappe')
            : 'frappe';
        const motion = readPreference(preferenceKeys.motion, 'system') === 'reduced' ? 'reduced' : 'system';
        document.documentElement.dataset.theme = theme;
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
        const permanent = document.getElementById('modePermanent').checked;
        summary.textContent = permanent
            ? t('privacy.summaryPermanent')
            : t('privacy.summaryFinite', { days: document.getElementById('retentionSlider').value });
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
        document.getElementById('saveSourceBtn').textContent =
            document.getElementById('sourceForm').dataset.editingId
                ? t('source.update')
                : t('source.save');
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
        if (!preview) {
            target.textContent = t('privacy.storagePending');
            return;
        }
        if (preview.retention_days === null) {
            target.textContent = t('privacy.previewPermanent');
            return;
        }
        const released = Math.max(preview.database_bytes - preview.estimated_database_bytes_after, 0);
        target.textContent = t('privacy.previewFinite', {
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
        renderSourcePasswordPlaceholder();
        renderSourceFormState();
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
    }

    async function refreshRetentionPreview() {
        const days = getRetentionDaysFromUi();
        const query = days === null ? '' : `?days=${encodeURIComponent(days)}`;
        const response = await apiFetch(`/api/privacy/retention/preview${query}`);
        if (!isResponseOk(response)) throw new Error('preview failed');
        const data = await response.json();
        state.storageSnapshot = data;
        updateStorageDisplay(data);
        updateRetentionPreviewText(data);
    }

    function scheduleRetentionPreview() {
        if (previewTimer) window.clearTimeout(previewTimer);
        previewTimer = window.setTimeout(() => {
            refreshRetentionPreview().catch(() => {
                showBanner('error', t('error.generic'));
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
                state.storageSnapshot = null;
                updateStorageDisplay(null);
                updateRetentionPreviewText(null);
            }
        } catch (error) {
            if (error.message === 'unauthorized') throw error;
            state.privacyStatus = 'error';
            renderPolicySummary();
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
        if (!username) {
            preview.textContent = t('privacy.userPreview', { count: 0 });
            return;
        }
        const response = await apiFetch(`/api/privacy/users/${encodeURIComponent(username)}/delete/preview`);
        if (!isResponseOk(response)) throw new Error('user preview failed');
        const data = await response.json();
        preview.textContent = t('privacy.userPreview', {
            count: localizedCount(data.records_to_delete),
        });
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
            url.textContent = server.url;
            identity.append(name, url);

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
                document.getElementById('sourceForm').dataset.editingId = server.id;
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
            const data = await response.json();
            document.getElementById('sourceUrl').value = data.url || '';
            document.getElementById('sourceUser').value = data.username || '';
            document.getElementById('sourcePass').value = '';
            state.sourcePasswordConfigured = Boolean(data.password_configured);
            renderSourcePasswordPlaceholder();
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
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ token }),
        });
        if (!response.ok) throw new Error('invalid token');
        hideLogin();
        await bootstrapData();
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
            options: [
                { value: 'en', label: 'English' },
                { value: 'zh-CN', label: '简体中文' },
            ],
            onChange: (language) => {
                i18n.setLocale(language);
                renderLocalizedState();
            },
        });
        createListbox('themeSelect', {
            value: readPreference(preferenceKeys.theme, 'frappe'),
            options: [
                { value: 'frappe', labelKey: 'preferences.themeFrappe' },
                { value: 'latte', labelKey: 'preferences.themeLatte' },
            ],
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
            onChange: () => refreshUserPreview().catch(() => {
                showBanner('error', t('error.generic'));
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
                refreshRetentionPreview().catch(() => showBanner('error', t('error.generic')));
            });
        });
        document.getElementById('retentionSlider').addEventListener('input', (event) => {
            document.getElementById('retentionValue').textContent = t('common.days', {
                count: event.target.value,
            });
            renderPolicySummary();
            scheduleRetentionPreview();
        });
        document.getElementById('saveRetentionBtn').addEventListener('click', async () => {
            try {
                const response = await apiFetch('/api/privacy/settings', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ retention_days: getRetentionDaysFromUi() }),
                });
                if (!isResponseOk(response)) throw new Error('save failed');
                state.privacyStatus = 'ready';
                renderPolicySummary();
                showBanner('success', t('privacy.retentionSaved'));
                await refreshRetentionPreview();
            } catch (error) {
                if (error.message !== 'unauthorized') showBanner('error', t('error.generic'));
            }
        });
        document.getElementById('applyRetentionBtn').addEventListener('click', async () => {
            const days = getRetentionDaysFromUi();
            if (days === null) {
                showBanner('error', t('privacy.noCleanup'));
                return;
            }
            try {
                await refreshRetentionPreview();
                const preview = document.getElementById('retentionPreview').textContent;
                if (!window.confirm(t('privacy.cleanupConfirm', { preview }))) return;
                const response = await apiFetch('/api/privacy/retention/apply', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ confirm: true }),
                });
                if (!isResponseOk(response)) throw new Error('cleanup failed');
                const data = await response.json();
                showBanner('success', t('privacy.cleanupSuccess', { count: localizedCount(data.deleted) }));
                await Promise.all([loadUsers(), refreshRetentionPreview()]);
            } catch (error) {
                if (error.message !== 'unauthorized') showBanner('error', t('privacy.cleanupFailed'));
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
                URL.revokeObjectURL(objectUrl);
                showBanner('success', t('privacy.exportSuccess', { username }));
            } catch (error) {
                if (error.message !== 'unauthorized') showBanner('error', t('privacy.exportFailed'));
            }
        });
        document.getElementById('importFile').addEventListener('change', async (event) => {
            const username = listboxes.get('userSelect').getValue();
            const file = event.target.files[0];
            event.target.value = '';
            if (!username || !file) return;
            try {
                const payload = JSON.parse(await file.text());
                const count = Array.isArray(payload.records) ? payload.records.length : 0;
                if (!window.confirm(t('privacy.importConfirm', {
                    username,
                    count: localizedCount(count),
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
                showBanner('success', t('privacy.importSuccess', { count: localizedCount(data.imported) }));
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
                await refreshUserPreview();
                const preview = document.getElementById('userPreview').textContent;
                if (!window.confirm(t('privacy.deleteConfirm', { preview, username }))) return;
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
        document.getElementById('sourceForm').addEventListener('submit', async (event) => {
            event.preventDefault();
            const form = event.currentTarget;
            const displayName = document.getElementById('sourceName').value.trim();
            const url = document.getElementById('sourceUrl').value.trim();
            const username = document.getElementById('sourceUser').value.trim();
            const password = document.getElementById('sourcePass').value;
            if (!displayName) return setSourceMessage('source.nameRequired', 'error');
            if (!url) return setSourceMessage('source.urlRequired', 'error');
            if (!username) return setSourceMessage('source.userRequired', 'error');
            try {
                const editingId = form.dataset.editingId;
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
                            enabled: true,
                        }),
                    },
                );
                if (!isResponseOk(response)) throw new Error('save failed');
                document.getElementById('sourcePass').value = '';
                form.removeAttribute('data-editing-id');
                renderSourceFormState();
                await Promise.all([loadServers(), loadSourceReadiness()]);
                setSourceMessage('source.saved', 'success');
            } catch (error) {
                if (error.message !== 'unauthorized') setSourceMessage('source.saveFailed', 'error');
            }
        });
        document.getElementById('testSourceBtn').addEventListener('click', async () => {
            setSourceMessage('source.testing');
            const payload = {};
            const url = document.getElementById('sourceUrl').value.trim();
            const username = document.getElementById('sourceUser').value.trim();
            const password = document.getElementById('sourcePass').value;
            if (url) payload.url = url;
            if (username) payload.username = username;
            if (password) payload.password = password;
            try {
                const response = await apiFetch('/api/source/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!isResponseOk(response)) throw new Error('test failed');
                const data = await response.json();
                setSourceMessage(data.ok ? 'source.testSuccess' : 'source.testFailure', data.ok ? 'success' : 'error');
            } catch (error) {
                if (error.message !== 'unauthorized') setSourceMessage('source.testFailed', 'error');
            }
        });
    }

    function bindAuthentication() {
        document.getElementById('loginForm').addEventListener('submit', async (event) => {
            event.preventDefault();
            try {
                await submitLogin(document.getElementById('loginToken').value);
            } catch (_error) {
                const error = document.getElementById('loginError');
                error.textContent = t('auth.invalid');
                error.hidden = false;
            }
        });
    }

    async function bootstrapData() {
        hideBanner();
        try {
            const statusResponse = await fetch('/api/auth/status', fetchOptions);
            if (statusResponse.ok) {
                const status = await statusResponse.json();
                if (status.auth_required) {
                    const probe = await fetch('/api/privacy/settings', fetchOptions);
                    if (probe.status === 401) {
                        showLogin();
                        return;
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
}());
