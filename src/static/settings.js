import { apiFetch, isAbortError, UnauthorizedError } from './js/http.js';
import { createLoginController } from './js/auth.js';
import { UNAUTHORIZED_EVENT } from './js/http.js';
import { readPreference, removePreference, writePreference } from './js/prefs.js';
import { createI18n } from './localization.js';

    const IMPORT_MAX_BYTES = 5 * 1024 * 1024;
    const preferenceKeys = Object.freeze({
        language: 'navidrome-language',
        theme: 'navidrome-theme',
        timezone: 'navidrome-timezone',
        motion: 'navidrome-motion',
    });

    const messages = {
        'zh-CN': {
            'page.title': '设置 · Navidrome Statistic',
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
            'source.passwordPlaceholder': '新增连接时必填',
            'source.passwordConfigured': '已配置 · 留空则保持不变',
            'source.passwordRequired': '新增连接需要填写密码。',
            'source.enabled': '采集此服务器',
            'source.enabledHelp': '禁用的连接仍会保留，但不会启动采集器。',
            'source.enabledStatus': '已启用',
            'source.disabledStatus': '已禁用',
            'source.save': '保存连接',
            'source.update': '更新连接',
            'source.cancelEdit': '取消编辑',
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
            'source.fallbackTitle': '环境变量回退连接',
            'source.fallbackDescription': '仅当没有任何已保存服务器时，NAVIDROME_URL、NAVIDROME_USER 与 NAVIDROME_PASS 才作为单服务器回退配置。已保存服务器作为独立连接使用。',
            'source.fallbackConfigured': '当前已配置回退连接：{username} · {url}',
            'source.fallbackMissing': '当前没有完整的环境变量或兼容回退连接。',
            'privacy.heading': '隐私与数据',
            'privacy.description': '控制行为数据的保留期限，并按用户导出或删除记录。',
            'privacy.currentPolicy': '当前保留策略',
            'privacy.policyLoading': '正在读取当前策略…',
            'privacy.policyLoadError': '未能读取策略。现有数据未被修改。',
            'privacy.retention': '数据保留',
            'privacy.retentionDescription': '保存有限策略后，服务会在启动时和后台维护期间自动删除超期记录；“立即应用”会现在执行一次。',
            'privacy.retentionMode': '保留方式',
            'privacy.finiteRetention': '指定天数',
            'privacy.finiteHelp': '1–360 天',
            'privacy.summaryPermanent': '永久保留，除非你主动删除。',
            'privacy.summaryFinite': '保留最近 {days} 天，超期记录会自动清理。',
            'privacy.previewPermanent': '播放记录会永久保留，除非按用户主动删除。',
            'privacy.previewFinite': '按 {label} 计算：将影响 {count} 条记录，预计释放 {bytes}。',
            'privacy.saveRetention': '保存策略',
            'privacy.cleanup': '立即应用',
            'privacy.retentionSaved': '保留策略已保存。有限策略会在启动和后台维护时自动执行。',
            'privacy.retentionSaveConfirm': '保存后，服务会自动删除超出该期限的记录。\n\n{preview}\n\n保存此有限保留策略吗？',
            'privacy.saveFirst': '请先保存当前保留策略，再立即应用。',
            'privacy.noCleanup': '当前为永久保留，无需清理。',
            'privacy.cleanupConfirm': '此操作不可撤销。\n\n{preview}\n\n立即删除这些超期记录吗？',
            'privacy.cleanupSuccess': '已清理 {count} 条超期记录。',
            'privacy.cleanupFailed': '清理失败，请重试。',
            'privacy.policyChanged': '保留策略已在其它会话中变更，页面已重新加载，未执行清理。',
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
            'privacy.importConfirm': '为“{username}”导入 {records} 条播放记录与 {attempts} 条短播放记录？',
            'privacy.importSuccess': '已导入 {records} 条播放记录与 {attempts} 条短播放记录。',
            'privacy.importTooLarge': '导入文件不能超过 5 MiB。',
            'privacy.importFailed': '导入失败，请检查 JSON 格式与用户名。',
            'privacy.deleteConfirm': '此操作不可撤销。\n\n{preview}\n\n确定删除用户“{username}”的全部播放数据吗？',
            'privacy.deleteSuccess': '已删除 {count} 条记录。',
            'privacy.deleteFailed': '删除失败。',
            'privacy.selectUserFirst': '请先选择用户。',
            'privacy.principles': '数据边界',
            'privacy.principleRetention': '播放历史、用户名、曲目、艺人、专辑与客户端名称均属于个人行为数据。',
            'privacy.principleCleanup': '有限保留策略会自动清理超期记录；立即清理和按用户删除会先提供影响预览并再次确认。',
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
            'page.title': 'Settings · Navidrome Statistic',
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
            'source.passwordPlaceholder': 'Required for a new connection',
            'source.passwordConfigured': 'Configured · leave blank to keep current',
            'source.passwordRequired': 'Enter a password for a new connection.',
            'source.enabled': 'Collect from this server',
            'source.enabledHelp': 'Disabled connections remain saved but do not run a collector.',
            'source.enabledStatus': 'Enabled',
            'source.disabledStatus': 'Disabled',
            'source.save': 'Save connection',
            'source.update': 'Update connection',
            'source.cancelEdit': 'Cancel edit',
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
            'source.fallbackTitle': 'Environment fallback connection',
            'source.fallbackDescription': 'NAVIDROME_URL, NAVIDROME_USER, and NAVIDROME_PASS provide one fallback connection only when no saved server entries exist. Saved servers are independent connections.',
            'source.fallbackConfigured': 'Fallback connection configured: {username} · {url}',
            'source.fallbackMissing': 'No complete environment or compatible fallback connection is configured.',
            'privacy.heading': 'Privacy & data',
            'privacy.description': 'Control how long behavioral data is kept, then export or delete records by user.',
            'privacy.currentPolicy': 'Current retention policy',
            'privacy.policyLoading': 'Reading the current policy…',
            'privacy.policyLoadError': 'The policy could not be loaded. Existing data was not changed.',
            'privacy.retention': 'Data retention',
            'privacy.retentionDescription': 'After a finite policy is saved, expired records are deleted automatically at startup and during background maintenance. “Apply now” runs it immediately.',
            'privacy.retentionMode': 'Retention mode',
            'privacy.finiteRetention': 'Keep for a period',
            'privacy.finiteHelp': '1–360 days',
            'privacy.summaryPermanent': 'Kept forever unless you explicitly delete it.',
            'privacy.summaryFinite': 'Keep the most recent {days} days. Older records are removed automatically.',
            'privacy.previewPermanent': 'Playback records are kept forever unless they are explicitly deleted by user.',
            'privacy.previewFinite': 'For {label}: {count} records affected, approximately {bytes} released.',
            'privacy.saveRetention': 'Save policy',
            'privacy.cleanup': 'Apply now',
            'privacy.retentionSaved': 'Retention policy saved. Finite policies run automatically at startup and during background maintenance.',
            'privacy.retentionSaveConfirm': 'After this is saved, the service automatically deletes records older than the selected period.\n\n{preview}\n\nSave this finite retention policy?',
            'privacy.saveFirst': 'Save the current retention policy before applying it now.',
            'privacy.noCleanup': 'Retention is permanent; no cleanup is needed.',
            'privacy.cleanupConfirm': 'This action cannot be undone.\n\n{preview}\n\nDelete these expired records now?',
            'privacy.cleanupSuccess': 'Deleted {count} expired records.',
            'privacy.cleanupFailed': 'Cleanup failed. Please try again.',
            'privacy.policyChanged': 'The retention policy changed in another session. Settings were reloaded and no cleanup was run.',
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
            'privacy.importConfirm': 'Import {records} plays and {attempts} short-play records for “{username}”?',
            'privacy.importSuccess': 'Imported {records} plays and {attempts} short-play records.',
            'privacy.importTooLarge': 'Import files cannot exceed 5 MiB.',
            'privacy.importFailed': 'Import failed. Check the JSON format and username.',
            'privacy.deleteConfirm': 'This action cannot be undone.\n\n{preview}\n\nDelete all playback data for “{username}”?',
            'privacy.deleteSuccess': 'Deleted {count} records.',
            'privacy.deleteFailed': 'Delete failed.',
            'privacy.selectUserFirst': 'Select a user first.',
            'privacy.principles': 'Data boundaries',
            'privacy.principleRetention': 'Playback history, usernames, tracks, artists, albums, and client names are all behavioral data.',
            'privacy.principleCleanup': 'Finite retention automatically removes expired records. Apply-now and per-user deletion show an impact preview and require confirmation.',
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
