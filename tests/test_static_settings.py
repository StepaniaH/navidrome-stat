"""Source-level checks for the settings information architecture and UI runtime."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_HTML = ROOT / "src" / "static" / "settings.html"
SETTINGS_JS = ROOT / "src" / "static" / "settings.js"
LOCALIZATION_JS = ROOT / "src" / "static" / "localization.js"
THEMES_JS = ROOT / "src" / "static" / "js" / "themes.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_settings_has_four_ordered_top_level_sections():
    source = _read(SETTINGS_HTML)
    names = ("source", "privacy", "preferences", "about")
    positions = [source.index(f'data-tab="{name}"') for name in names]
    assert positions == sorted(positions)
    tab_markup = source[source.index('id="settingsTabBar"') : source.index("</nav>")]
    assert tab_markup.count('role="tab"') == 4
    assert tab_markup.count("<svg") == 4
    for name in names:
        assert f'id="tab-{name}-btn"' in tab_markup
        assert f'id="tab-{name}"' in source
    assert 'data-tab="general"' not in source
    assert 'data-tab="appearance"' not in source


def test_settings_uses_one_aligned_surface_and_flat_sections():
    source = _read(SETTINGS_HTML)
    assert "grid-template-columns: 206px minmax(0, 1fr)" in source
    assert 'class="settings-navigation"' in source
    assert 'class="settings-panel"' in source
    assert 'class="settings-section"' in source
    assert ".settings-section {" in source
    assert "border-top: 1px solid var(--border-soft)" in source
    assert "rounded-2xl" not in source
    assert "bg-ink-900/80" not in source
    assert "mesh-bg" not in source


def test_source_message_stays_in_normal_flow():
    source = _read(SETTINGS_HTML)
    message = source[source.index('id="sourceMessage"') - 120 : source.index('id="sourceMessage"') + 190]
    assert "source-message" in message
    assert 'aria-live="polite"' in message
    css = source[source.index(".source-message {") : source.index(".server-list {")]
    assert "position: static" in css
    assert "margin-top" in css
    assert "absolute" not in css


def test_all_settings_selectors_use_the_shared_custom_listbox():
    html = _read(SETTINGS_HTML)
    script = _read(SETTINGS_JS)
    assert "<select" not in html
    for control_id in (
        "languageSelect",
        "settingsTimezoneSelect",
        "userSelect",
    ):
        assert f'id="{control_id}"' in html
        assert f"createListbox('{control_id}'" in script
    assert html.count('aria-haspopup="listbox"') == 3
    assert html.count('role="listbox"') == 3
    assert 'id="themeSelect"' not in html
    assert "createListbox('themeSelect'" not in script
    assert "function createListbox(" in script
    for key in ("ArrowDown", "ArrowUp", "Home", "End", "Escape", "Tab"):
        assert f"event.key === '{key}'" in script
    assert "aria-selected" in script
    assert "restoreFocus" in script


def test_theme_controls_use_separate_mode_and_palette_pickers():
    html = _read(SETTINGS_HTML)
    script = _read(SETTINGS_JS)
    for picker_id in ("themeModePicker", "themePalettePicker"):
        assert f'id="{picker_id}"' in html
        assert picker_id in script
    assert "THEME_MODES" in script
    assert "PALETTES" in script
    assert "preview.dataset.theme = previewTheme" in script
    assert "querySelector('.theme-swatch-preview').dataset.theme" in script
    assert "darkHalf.dataset.theme = 'builtin-dark'" in script
    assert "lightHalf.dataset.theme = 'builtin-light'" in script
    assert ".theme-swatch-half {" in html
    assert "data-theme-preview" not in html
    assert "data-theme-preview" not in script
    assert "themeLabelKey" not in script
    assert "themeValue" not in script


def test_theme_catalogs_do_not_keep_obsolete_concrete_variant_labels():
    locale_dir = ROOT / "src" / "static" / "js" / "i18n" / "locales"
    obsolete_keys = (
        "common.scheme.dark",
        "common.scheme.light",
        "preferences.theme.frappe",
        "preferences.theme.latte",
        "preferences.theme.macchiato",
        "preferences.theme.mocha",
        "preferences.theme.nord",
        "preferences.theme.dracula",
        "preferences.theme.tokyo-night",
        "preferences.theme.gruvbox-dark",
        "preferences.theme.solarized-dark",
        "preferences.theme.solarized-light",
    )
    for locale_file in locale_dir.glob("*.js"):
        catalog = _read(locale_file)
        for key in obsolete_keys:
            assert key not in catalog, f"{key} is obsolete in {locale_file.name}"


def test_dynamic_privacy_policy_is_not_a_static_translation_target():
    html = _read(SETTINGS_HTML)
    script = _read(SETTINGS_JS)
    policy_markup = html[html.index('id="policySummary"') - 80 : html.index('id="policySummary"') + 220]
    assert "data-i18n=" not in policy_markup
    assert 'data-state="loading"' in policy_markup
    assert "function renderPolicySummary()" in script
    assert "state.privacyStatus = 'ready'" in script
    assert "state.privacyStatus = 'error'" in script
    assert "privacy.policyLoadError" in script
    assert "summary.closest('.status-line').dataset.state" in script
    assert "renderLocalizedState()" in script


def test_shared_localization_runtime_has_fallback_interpolation_and_dom_translation():
    html = _read(SETTINGS_HTML)
    settings_script = _read(SETTINGS_JS)
    runtime = _read(LOCALIZATION_JS)
    assert '<script type="module" src="/static/localization.js"></script>' in html
    assert '<script type="module" src="/static/settings.js"></script>' in html
    assert "function normalizeLocale(" in runtime
    assert "function interpolate(" in runtime
    assert "localizedMessage ?? fallbackMessage ?? key" in runtime
    assert "element.textContent = t(element.dataset.i18n)" in runtime
    assert "data-i18n-attr" in runtime
    assert "createI18n({ messages: pageMessages('settings'), fallbackLocale: 'en' })" in settings_script
    locale_files = {path.stem for path in (ROOT / "src" / "static" / "js" / "i18n" / "locales").glob("*.js")}
    assert {"zh-CN", "zh-TW", "en", "ja", "de"} <= locale_files
    assert "'zh-CN': {" not in settings_script
    assert "localized(" not in settings_script


def test_local_preferences_include_motion_and_reset_without_server_writes():
    script = _read(SETTINGS_JS)
    html = _read(SETTINGS_HTML)
    for key in (
        "navidrome-language",
        "navidrome-timezone",
        "navidrome-motion",
    ):
        assert key in script
    themes = _read(THEMES_JS)
    for key in (
        "navidrome-theme",
        "navidrome-theme-mode",
        "navidrome-theme-palette",
    ):
        assert key in themes
    assert "APPEARANCE_PREFERENCE_KEYS" in script
    assert 'id="motionToggle"' in html
    assert 'id="privacyFirstRun"' in html
    assert 'data-i18n="privacy.firstRunNote"' in html
    script_block = script[script.index("function renderServers()") :]
    assert "privacyFirstRun" in script_block
    assert 'role="switch"' in html
    assert 'id="resetPreferencesBtn"' in html
    assert "Object.values(preferenceKeys)" in script
    assert "Object.values(APPEARANCE_PREFERENCE_KEYS)" in script
    assert "removePreference" in script
    assert "document.documentElement.dataset.motion = motion" in script
    preferences_block = script[
        script.index("function bindPreferenceControls()")
        : script.index("function bindPrivacyControls()")
    ]
    assert "apiFetch(" not in preferences_block
    assert "fetch(" not in preferences_block


def test_settings_loads_shared_theme_assets_and_registry():
    html = _read(SETTINGS_HTML)
    script = _read(SETTINGS_JS)
    assert '<link rel="stylesheet" href="/static/themes.css">' in html
    assert '<script type="module" src="/static/theme-bootstrap.js"></script>' in html
    assert "{ value: 'browser'" in script
    assert "{ value: 'UTC'" in script
    assert "APPEARANCE_PREFERENCE_KEYS" in script
    assert "applyStoredAppearance" in script


def test_sensitive_values_use_safe_dom_apis_and_password_is_never_rendered():
    html = _read(SETTINGS_HTML)
    script = _read(SETTINGS_JS)
    assert 'id="sourcePass"' in html
    assert 'type="password"' in html
    assert "innerHTML" not in script
    assert "insertAdjacentHTML" not in script
    assert "textContent" in script
    assert "password_configured" in script
    assert "sourcePass').value = data." not in script
    assert "link.download = 'navidrome-stat-export.json'" in script
    assert "navidrome-stat-${username" not in script
    assert "console.log" not in script


def test_server_settings_apply_immediately_without_restart_copy():
    script = _read(SETTINGS_JS)
    zh_catalog = _read(ROOT / "src" / "static" / "js" / "i18n" / "locales" / "zh-CN.js")
    en_catalog = _read(ROOT / "src" / "static" / "js" / "i18n" / "locales" / "en.js")
    assert "连接更改保存后立即应用" in zh_catalog
    assert "Saved changes apply immediately" in en_catalog
    assert "连接已保存并立即应用" in zh_catalog
    assert "Connection saved and applied immediately" in en_catalog
    assert "重启服务后生效" not in script
    assert "Restart the service to apply it" not in script


def test_retention_copy_matches_automatic_cleanup_and_apply_uses_saved_policy():
    html = _read(SETTINGS_HTML)
    script = _read(SETTINGS_JS)
    assert "deleted automatically at startup and during background maintenance" in html
    zh_catalog = _read(ROOT / "src" / "static" / "js" / "i18n" / "locales" / "zh-CN.js")
    assert "有限策略会在启动和后台维护时自动执行" in zh_catalog
    assert "Records are deleted only after" not in html
    assert "只有点击“确认清理”才会删除" not in script
    assert "function retentionDraftIsDirty()" in script
    assert "expected_retention_days: persistedDays" in script
    assert "response.status === 409" in script
    assert "applyRetentionBtn').disabled = !persistedFinite || dirty" in script


def test_source_form_has_explicit_create_and_edit_modes():
    html = _read(SETTINGS_HTML)
    script = _read(SETTINGS_JS)
    assert 'id="cancelSourceEditBtn"' in html
    source_pass_line = next(line for line in html.splitlines() if 'id="sourcePass"' in line)
    assert "required" in source_pass_line
    assert 'id="sourceEnabled"' in html
    assert "function resetSourceForm()" in script
    assert "password.required = !editing" in script
    assert "const enabled = document.getElementById('sourceEnabled').checked" in script
    assert "statusBadge.dataset.enabled = String(Boolean(server.enabled))" in script
    assert "sourceEditingEnabled" not in script
    assert "`/api/servers/${encodeURIComponent(editingId)}/test`" in script
    assert "state.fallbackSourceConfig = await response.json()" in script
    assert "always take precedence" not in script


def test_destructive_previews_ignore_stale_responses_and_import_is_keyboard_reachable():
    html = _read(SETTINGS_HTML)
    script = _read(SETTINGS_JS)
    assert "new AbortController()" in script
    assert "retentionPreviewController !== controller" in script
    assert "userPreviewController !== controller" in script
    assert "preview.username !== username" in script
    assert 'id="importBtn"' in html
    assert 'id="importFile" class="visually-hidden"' in html
    assert "file.size > IMPORT_MAX_BYTES" in script
    assert "attempts_imported" in script


def test_settings_login_is_an_accessible_dialog():
    html = _read(SETTINGS_HTML)
    script = _read(SETTINGS_JS)
    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'aria-labelledby="settingsLoginTitle"' in html
    assert 'id="loginError" class="login-error" role="alert"' in html
    assert "inertSelector: '.settings-shell'" in script
    assert "login.bind()" in script
    auth_js = _read(ROOT / "src" / "static" / "js" / "auth.js")
    assert "shell().inert" in auth_js
    assert "requestAnimationFrame" in auth_js
    assert "event.key" in _read(ROOT / "src/static/js/auth.js")
    assert "tokenInput.value = ''" in script


def test_about_panel_has_version_row_served_by_api():
    html = _read(SETTINGS_HTML)
    assert 'data-i18n="about.version"' in html
    assert "data-app-version" in html


def test_settings_runtime_fills_version_from_about_endpoint():
    js = _read(SETTINGS_JS)
    assert "applyAppVersion" in js
    assert '"/api/about"' not in js  # fetched via js/app-info.js, not inline


def test_server_row_test_result_renders_inline_not_in_form():
    js = _read(SETTINGS_JS)
    assert "server-test-status" in js
    html = _read(SETTINGS_HTML)
    assert ".server-test-status" in html


def test_server_form_has_backfill_playlist_field_with_help():
    html = _read(SETTINGS_HTML)
    assert 'id="sourceBackfillPlaylist"' in html
    assert 'for="sourceBackfillPlaylist"' in html
    assert 'data-i18n="source.backfillPlaylist"' in html
    assert "source.backfillHelp" in html


def test_settings_js_round_trips_backfill_playlist_id():
    script = _read(SETTINGS_JS)
    assert "sourceBackfillPlaylist" in script
    assert "backfill_playlist_id" in script


def test_settings_row_surfaces_backfill_status_only_when_configured():
    script = _read(SETTINGS_JS)
    assert "backfillStatusLine" in script or "server-backfill-status" in script
    assert "source.backfillStatus" in script
