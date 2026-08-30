import { readPreference, writePreference } from '../prefs.js';
import {
    APPEARANCE_PREFERENCE_KEYS,
    PALETTES,
    THEME_MODES,
    paletteTheme,
} from '../themes.js';
import {
    CUSTOM_THEME_FIELDS,
    applyThemeCustomization,
    decodeThemeDocument,
    encodeThemeDocument,
    normalizeHexColor,
    readThemeCustomizations,
    removeThemeCustomization,
    saveThemeCustomization,
    themeCustomizationFor,
    validateThemeCustomization,
} from '../theme-customization.js';
import { THEME_CHANGE_EVENT, applyStoredAppearance } from '../../theme-bootstrap.js';

const IMPORT_MAX_BYTES = 16 * 1024;

export function createAppearanceSettings({ t, confirmDiscard = window.confirm }) {
    let currentAppearance = null;
    let baseColors = null;
    let committedColors = null;
    let dirty = false;
    let themeId = null;
    let mounted = false;
    let suppressDetailsToggle = false;

    function createSwatch({ group, value, previewTheme, systemPreview = false }) {
        const swatch = document.createElement('label');
        swatch.className = 'theme-swatch';
        const input = document.createElement('input');
        input.type = 'radio';
        input.name = group;
        input.value = value;
        const preview = document.createElement('span');
        preview.className = `theme-swatch-preview${systemPreview ? ' is-system' : ''}`;
        preview.setAttribute('aria-hidden', 'true');
        if (previewTheme) preview.dataset.theme = previewTheme;
        if (systemPreview) {
            for (const concrete of ['builtin-dark', 'builtin-light']) {
                const half = document.createElement('span');
                half.className = 'theme-swatch-half';
                half.dataset.theme = concrete;
                preview.appendChild(half);
            }
        } else {
            preview.append(
                document.createElement('i'),
                document.createElement('i'),
                document.createElement('i'),
            );
        }
        const name = document.createElement('span');
        name.className = 'theme-swatch-name';
        swatch.append(input, preview, name);
        return swatch;
    }

    function buildPickers() {
        document.getElementById('themeModePicker').replaceChildren(
            ...THEME_MODES.map((mode) => createSwatch({
                group: 'theme-mode',
                value: mode,
                previewTheme: mode === 'system' ? null : `builtin-${mode}`,
                systemPreview: mode === 'system',
            })),
        );
        document.getElementById('themePalettePicker').replaceChildren(
            ...PALETTES.map((palette) => createSwatch({
                group: 'theme-palette',
                value: palette.id,
                previewTheme: palette.variants.dark,
            })),
        );
    }

    function syncPickers(appearance) {
        if (!appearance) return;
        currentAppearance = appearance;
        const customizations = readThemeCustomizations();
        document.querySelectorAll('input[name="theme-mode"]').forEach((input) => {
            input.checked = input.value === appearance.mode;
            const label = t(`preferences.themeMode.${input.value}`);
            input.setAttribute('aria-label', label);
            const swatch = input.closest('.theme-swatch');
            swatch.querySelector('.theme-swatch-name').textContent = label;
        });
        document.querySelectorAll('input[name="theme-palette"]').forEach((input) => {
            const palette = PALETTES.find((entry) => entry.id === input.value);
            const swatch = input.closest('.theme-swatch');
            const label = t(`preferences.palette.${input.value}`);
            input.checked = input.value === appearance.palette;
            input.setAttribute('aria-label', label);
            swatch.classList.toggle(
                'is-customized',
                input.checked && Boolean(themeCustomizationFor(appearance.theme, customizations)),
            );
            swatch.querySelector('.theme-swatch-preview').dataset.theme = (
                paletteTheme(input.value, appearance.scheme)
                || palette?.variants.dark
                || 'builtin-dark'
            );
            swatch.querySelector('.theme-swatch-name').textContent = label;
        });
    }

    function colorsMatch(first, second) {
        return Boolean(first && second) && CUSTOM_THEME_FIELDS.every(
            ({ key }) => first[key] === second[key],
        );
    }

    function computedColorToHex(raw) {
        const value = String(raw || '').trim();
        const direct = normalizeHexColor(value);
        if (direct) return direct;
        const match = value.match(/^rgba?\(\s*(\d+)\s*[, ]\s*(\d+)\s*[, ]\s*(\d+)/i);
        if (!match) return null;
        return `#${match.slice(1, 4).map((channel) => (
            Math.max(0, Math.min(255, Number(channel))).toString(16).padStart(2, '0')
        )).join('')}`;
    }

    function snapshotPreset(concreteTheme) {
        const probe = document.createElement('span');
        probe.dataset.theme = concreteTheme;
        probe.hidden = true;
        document.body.appendChild(probe);
        const styles = window.getComputedStyle(probe);
        const colors = Object.fromEntries(CUSTOM_THEME_FIELDS.map(({ key, property }) => [
            key,
            computedColorToHex(styles.getPropertyValue(property)),
        ]));
        probe.remove();
        return validateThemeCustomization(colors).colors;
    }

    function values() {
        return Object.fromEntries(CUSTOM_THEME_FIELDS.map(({ key }) => [
            key,
            document.querySelector(`[data-theme-hex="${key}"]`)?.value || '',
        ]));
    }

    function setStatus(key = '', kind = '', replacements) {
        const status = document.getElementById('themeCustomizationStatus');
        status.textContent = key ? t(key, replacements) : '';
        if (kind) status.dataset.kind = kind;
        else delete status.dataset.kind;
    }

    function renderChecks(validation) {
        const target = document.getElementById('themeContrastChecks');
        target.replaceChildren();
        if (!validation.colors) return;
        for (const foreground of ['text', 'muted', 'accent']) {
            const checks = validation.checks.filter((check) => check.foreground === foreground);
            const passes = checks.every((check) => check.pass);
            const item = document.createElement('li');
            item.dataset.pass = String(passes);
            item.textContent = t(`preferences.themeEditor.${passes ? 'contrastGroupPass' : 'contrastGroupFail'}`, {
                foreground: t(`preferences.themeEditor.${foreground}`),
            });
            target.appendChild(item);
        }
    }

    function updateActions(validation = validateThemeCustomization(values())) {
        const draft = values();
        dirty = Boolean(committedColors) && CUSTOM_THEME_FIELDS.some(
            ({ key }) => normalizeHexColor(draft[key]) !== committedColors[key],
        );
        document.getElementById('saveThemeCustomizationBtn').disabled = !dirty || !validation.valid;
        renderChecks(validation);
        return validation;
    }

    function preview(colors) {
        if (!themeId || !currentAppearance) return;
        applyThemeCustomization(document.documentElement, themeId, colors);
        window.dispatchEvent(new CustomEvent(THEME_CHANGE_EVENT, {
            detail: { ...currentAppearance, preview: true },
        }));
    }

    function setValues(colors, { live = false } = {}) {
        if (!colors) return;
        for (const { key } of CUSTOM_THEME_FIELDS) {
            const color = document.querySelector(`[data-theme-color="${key}"]`);
            const hex = document.querySelector(`[data-theme-hex="${key}"]`);
            color.value = colors[key];
            hex.value = colors[key];
            hex.setAttribute('aria-invalid', 'false');
        }
        const validation = updateActions(validateThemeCustomization(colors));
        if (live && validation.colors) preview(validation.colors);
    }

    function renderLabels() {
        document.querySelectorAll('[data-theme-field-label]').forEach((label) => {
            label.textContent = t(`preferences.themeEditor.${label.dataset.themeFieldLabel}`);
        });
        document.querySelectorAll('[data-theme-hex]').forEach((input) => {
            input.setAttribute('aria-label', t('preferences.themeEditor.hex', {
                color: t(`preferences.themeEditor.${input.dataset.themeHex}`),
            }));
        });
        document.querySelectorAll('[data-theme-copy]').forEach((button) => {
            button.setAttribute('aria-label', t('preferences.themeEditor.copyColor', {
                color: t(`preferences.themeEditor.${button.dataset.themeCopy}`),
            }));
            button.title = t('preferences.themeEditor.copy');
        });
        if (!currentAppearance || !themeId) return;
        const customized = Boolean(themeCustomizationFor(themeId, readThemeCustomizations()));
        document.getElementById('themeCustomizationBase').textContent = t(
            customized ? 'preferences.themeEditor.baseCustomized' : 'preferences.themeEditor.base',
            {
                mode: t(`preferences.themeMode.${currentAppearance.scheme}`),
                palette: t(`preferences.palette.${currentAppearance.palette}`),
            },
        );
        renderChecks(validateThemeCustomization(values()));
    }

    function syncEditor(appearance = currentAppearance) {
        if (!appearance) return;
        const preset = snapshotPreset(appearance.theme);
        if (!preset) {
            setStatus('preferences.themeEditor.readFailed', 'error');
            return;
        }
        themeId = appearance.theme;
        baseColors = { ...preset };
        committedColors = {
            ...(themeCustomizationFor(appearance.theme, readThemeCustomizations()) || preset),
        };
        dirty = false;
        setValues(committedColors);
        setStatus();
        renderLabels();
    }

    function buildEditor() {
        const rows = CUSTOM_THEME_FIELDS.map(({ key }) => {
            const row = document.createElement('div');
            row.className = 'theme-color-row';
            const label = document.createElement('label');
            label.htmlFor = `themeColor-${key}`;
            label.dataset.themeFieldLabel = key;
            const color = document.createElement('input');
            color.id = `themeColor-${key}`;
            color.type = 'color';
            color.dataset.themeColor = key;
            const hex = document.createElement('input');
            hex.type = 'text';
            hex.maxLength = 7;
            hex.spellcheck = false;
            hex.autocomplete = 'off';
            hex.dataset.themeHex = key;
            const copy = document.createElement('button');
            copy.type = 'button';
            copy.className = 'theme-copy-button';
            copy.dataset.themeCopy = key;
            copy.textContent = '⧉';
            row.append(label, color, hex, copy);
            return row;
        });
        document.getElementById('themeCustomizationFields').replaceChildren(...rows);
        renderLabels();
    }

    function handleInput(event) {
        const colorInput = event.target.closest('[data-theme-color]');
        const hexInput = event.target.closest('[data-theme-hex]');
        if (!colorInput && !hexInput) return;
        const key = colorInput?.dataset.themeColor || hexInput.dataset.themeHex;
        if (colorInput) {
            const paired = document.querySelector(`[data-theme-hex="${key}"]`);
            paired.value = colorInput.value;
            paired.setAttribute('aria-invalid', 'false');
        } else {
            const normalized = normalizeHexColor(hexInput.value);
            hexInput.setAttribute('aria-invalid', normalized ? 'false' : 'true');
            if (normalized) {
                hexInput.value = normalized;
                document.querySelector(`[data-theme-color="${key}"]`).value = normalized;
            }
        }
        const validation = updateActions();
        if (!validation.colors) {
            setStatus('preferences.themeEditor.invalidHex', 'error');
            return;
        }
        preview(validation.colors);
        setStatus(
            validation.valid
                ? (dirty ? 'preferences.themeEditor.previewing' : '')
                : 'preferences.themeEditor.lowContrast',
            validation.valid ? '' : 'error',
        );
    }

    function cancel() {
        applyStoredAppearance();
        syncEditor(currentAppearance);
    }

    function discardIfNeeded() {
        if (!dirty) return true;
        if (!confirmDiscard(t('preferences.themeEditor.discardConfirm'))) return false;
        cancel();
        return true;
    }

    function save() {
        const validation = validateThemeCustomization(values());
        if (!validation.valid) {
            setStatus(
                validation.colors
                    ? 'preferences.themeEditor.lowContrast'
                    : 'preferences.themeEditor.invalidHex',
                'error',
            );
            return;
        }
        const restored = colorsMatch(validation.colors, baseColors);
        const saved = restored
            ? removeThemeCustomization(themeId)
            : saveThemeCustomization(themeId, validation.colors);
        if (!saved) {
            setStatus('preferences.themeEditor.saveFailed', 'error');
            return;
        }
        applyStoredAppearance();
        syncPickers(currentAppearance);
        syncEditor(currentAppearance);
        setStatus(
            restored ? 'preferences.themeEditor.restored' : 'preferences.themeEditor.saved',
            'success',
        );
    }

    async function copyColor(key) {
        const value = document.querySelector(`[data-theme-hex="${key}"]`).value;
        try {
            await navigator.clipboard.writeText(value);
            setStatus('preferences.themeEditor.copied', 'success', { color: value });
        } catch (_error) {
            setStatus('preferences.themeEditor.copyFailed', 'error');
        }
    }

    function exportDocument() {
        const encoded = encodeThemeDocument(themeId, values());
        if (!encoded) {
            setStatus('preferences.themeEditor.exportInvalid', 'error');
            return;
        }
        const url = URL.createObjectURL(new Blob([encoded], { type: 'application/json' }));
        const link = document.createElement('a');
        link.href = url;
        link.download = `navidrome-theme-${themeId}.json`;
        link.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 0);
        setStatus('preferences.themeEditor.exported', 'success');
    }

    async function importDocument(file) {
        if (!file) return;
        if (file.size > IMPORT_MAX_BYTES) {
            setStatus('preferences.themeEditor.importTooLarge', 'error');
            return;
        }
        let decoded;
        try {
            decoded = decodeThemeDocument(await file.text(), themeId);
        } catch (_error) {
            setStatus('preferences.themeEditor.importError.invalid_document', 'error');
            return;
        }
        if (!decoded.valid) {
            setStatus(`preferences.themeEditor.importError.${decoded.error}`, 'error');
            return;
        }
        setValues(decoded.colors, { live: true });
        setStatus('preferences.themeEditor.importPreview', 'success');
    }

    function selectAppearance(mode, palette) {
        if (!discardIfNeeded()) {
            syncPickers(currentAppearance);
            return;
        }
        writePreference(APPEARANCE_PREFERENCE_KEYS.mode, mode);
        writePreference(APPEARANCE_PREFERENCE_KEYS.palette, palette);
        const appearance = applyStoredAppearance();
        writePreference(APPEARANCE_PREFERENCE_KEYS.legacyTheme, appearance.theme);
        syncPickers(appearance);
        syncEditor(appearance);
    }

    function mount() {
        if (mounted) return;
        mounted = true;
        buildPickers();
        buildEditor();
        document.getElementById('themeModePicker').addEventListener('change', (event) => {
            if (event.target.matches('input[name="theme-mode"]')) {
                selectAppearance(event.target.value, currentAppearance?.palette || 'builtin');
            }
        });
        document.getElementById('themePalettePicker').addEventListener('change', (event) => {
            if (event.target.matches('input[name="theme-palette"]')) {
                selectAppearance(currentAppearance?.mode || 'system', event.target.value);
            }
        });
        document.getElementById('themeCustomizationFields').addEventListener('input', handleInput);
        document.getElementById('themeCustomizationFields').addEventListener('click', (event) => {
            const button = event.target.closest('[data-theme-copy]');
            if (button) copyColor(button.dataset.themeCopy);
        });
        document.getElementById('restoreThemePresetBtn').addEventListener('click', () => {
            setValues(baseColors, { live: true });
            setStatus('preferences.themeEditor.presetPreview');
        });
        document.getElementById('cancelThemePreviewBtn').addEventListener('click', cancel);
        document.getElementById('saveThemeCustomizationBtn').addEventListener('click', save);
        document.getElementById('exportThemeCustomizationBtn').addEventListener('click', exportDocument);
        document.getElementById('importThemeCustomizationBtn').addEventListener('click', () => {
            document.getElementById('themeCustomizationFile').click();
        });
        document.getElementById('themeCustomizationFile').addEventListener('change', async (event) => {
            await importDocument(event.target.files?.[0]);
            event.target.value = '';
        });
        document.getElementById('themeCustomization').addEventListener('toggle', (event) => {
            if (suppressDetailsToggle || event.currentTarget.open || !dirty) return;
            if (discardIfNeeded()) return;
            suppressDetailsToggle = true;
            event.currentTarget.open = true;
            queueMicrotask(() => { suppressDetailsToggle = false; });
        });
        window.addEventListener('beforeunload', (event) => {
            if (!dirty) return;
            event.preventDefault();
            event.returnValue = '';
        });
        window.addEventListener(THEME_CHANGE_EVENT, (event) => {
            syncPickers(event.detail);
            if (!event.detail.preview) syncEditor(event.detail);
        });
    }

    function apply() {
        const appearance = applyStoredAppearance();
        syncPickers(appearance);
        if (mounted) syncEditor(appearance);
        return appearance;
    }

    return {
        apply,
        localize: renderLabels,
        mount,
    };
}
