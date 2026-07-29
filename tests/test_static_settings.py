"""Source-level checks for the settings information architecture and UI runtime."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_HTML = ROOT / "src" / "static" / "settings.html"
SETTINGS_JS = ROOT / "src" / "static" / "settings.js"
LOCALIZATION_JS = ROOT / "src" / "static" / "localization.js"


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
        "themeSelect",
        "settingsTimezoneSelect",
        "userSelect",
    ):
        assert f'id="{control_id}"' in html
        assert f"createListbox('{control_id}'" in script
    assert html.count('aria-haspopup="listbox"') == 4
    assert html.count('role="listbox"') == 4
    assert "function createListbox(" in script
    for key in ("ArrowDown", "ArrowUp", "Home", "End", "Escape", "Tab"):
        assert f"event.key === '{key}'" in script
    assert "aria-selected" in script
    assert "restoreFocus" in script


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
    assert '<script src="/static/localization.js"></script>' in html
    assert '<script src="/static/settings.js"></script>' in html
    assert "function normalizeLocale(" in runtime
    assert "function interpolate(" in runtime
    assert "localizedMessage ?? fallbackMessage ?? key" in runtime
    assert "element.textContent = t(element.dataset.i18n)" in runtime
    assert "data-i18n-attr" in runtime
    assert "createI18n({ messages, fallbackLocale: 'en' })" in settings_script
    assert "'zh-CN': {" in settings_script
    assert "en: {" in settings_script
    assert "function localized(" not in settings_script
    assert "localized(" not in settings_script


def test_local_preferences_include_motion_and_reset_without_server_writes():
    script = _read(SETTINGS_JS)
    html = _read(SETTINGS_HTML)
    for key in (
        "navidrome-language",
        "navidrome-theme",
        "navidrome-timezone",
        "navidrome-motion",
    ):
        assert key in script
    assert 'id="motionToggle"' in html
    assert 'role="switch"' in html
    assert 'id="resetPreferencesBtn"' in html
    assert "Object.values(preferenceKeys).forEach(removePreference)" in script
    assert "document.documentElement.dataset.motion = motion" in script
    preferences_block = script[
        script.index("function bindPreferenceControls()")
        : script.index("function bindPrivacyControls()")
    ]
    assert "apiFetch(" not in preferences_block
    assert "fetch(" not in preferences_block


def test_settings_has_timezone_and_catppuccin_palette_tokens():
    html = _read(SETTINGS_HTML)
    script = _read(SETTINGS_JS)
    assert 'id="settingsTimezoneSelect"' in html
    assert "{ value: 'browser'" in script
    assert "{ value: 'UTC'" in script
    for token in (
        "#303446",
        "#292c3c",
        "#ca9ee6",
        "#a6d189",
        "#eff1f5",
        "#8839ef",
        "#40a02b",
    ):
        assert token in html


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
    assert "连接更改保存后立即应用" in script
    assert "Saved changes apply immediately" in script
    assert "连接已保存并立即应用" in script
    assert "Connection saved and applied immediately" in script
    assert "重启服务后生效" not in script
    assert "Restart the service to apply it" not in script
