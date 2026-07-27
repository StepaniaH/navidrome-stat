"""Source-level checks for settings layout, preferences, and accessibility."""

from pathlib import Path


SETTINGS_HTML = Path(__file__).resolve().parent.parent / "src" / "static" / "settings.html"


def test_settings_tabs_are_ordered_and_have_icons():
    source = SETTINGS_HTML.read_text(encoding="utf-8")
    positions = [source.index(f'data-tab="{name}"') for name in ("source", "privacy", "general", "appearance", "about")]
    assert positions == sorted(positions)
    tab_markup = source[source.index('id="settingsTabBar"') : source.index("</nav>")]
    assert tab_markup.count('role="tab"') == 5
    assert tab_markup.count("<svg") == 5
    assert tab_markup.count('class="w-4 h-4 shrink-0 text-accent"') == 5
    assert tab_markup.count('fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" viewBox="0 0 24 24"') == 5
    assert 'text-mint' not in tab_markup
    for name in ("source", "privacy", "general", "appearance", "about"):
        assert f'data-tab="{name}"' in tab_markup


def test_settings_tabs_and_detail_share_aligned_shell():
    source = SETTINGS_HTML.read_text(encoding="utf-8")
    layout = source[source.index('<div class="settings-layout">') : source.index("</main>")]
    assert 'class="settings-layout"' in source
    assert "grid-template-columns: 13rem minmax(0, 1fr)" in source
    assert "align-items: start" in source
    assert 'class="flex flex-col md:flex-row gap-6"' not in source
    assert 'class="flex md:flex-col gap-1 sticky top-4"' in layout
    assert 'bg-ink-900/80 border border-white/5 sticky top-4' not in layout


def test_source_message_stays_in_normal_flow():
    source = SETTINGS_HTML.read_text(encoding="utf-8")
    message = source[source.index('id="sourceMessage"') - 100 : source.index('id="sourceMessage"') + 180]
    assert "source-message" in message
    assert 'aria-live="polite"' in message
    css = source[source.index(".source-message") : source.index(".retention-mode")]
    assert "position: static" in css
    assert "margin-top" in css
    assert "absolute" not in css


def test_settings_i18n_and_local_preferences_are_local_only():
    source = SETTINGS_HTML.read_text(encoding="utf-8")
    assert '<html lang="en">' in source
    assert "localStorage.getItem('navidrome-language') || 'en'" in source
    for key in ("navidrome-language", "navidrome-theme", "navidrome-timezone"):
        assert key in source
    assert "data-i18n=\"tab.source\"" in source
    assert "data-i18n=\"tab.general\"" in source
    assert "function translatePage()" in source
    assert "element.textContent = t(element.dataset.i18n)" in source
    assert "data-i18n-attr" in source
    assert "function localized(" in source


def test_settings_has_timezone_and_catppuccin_palette_tokens():
    source = SETTINGS_HTML.read_text(encoding="utf-8")
    assert 'id="settingsTimezoneSelect"' in source
    assert 'value="browser"' in source
    assert 'value="UTC"' in source
    for token in ("#303446", "#292c3c", "#ca9ee6", "#a6d189", "#eff1f5", "#e6e9ef", "#8839ef", "#40a02b"):
        assert token in source


def test_server_settings_apply_immediately_without_restart_copy():
    source = SETTINGS_HTML.read_text(encoding="utf-8")
    assert "服务器配置保存后立即应用" in source
    assert "Server changes apply immediately" in source
    assert "重启服务后生效" not in source
    assert "Restart the service to apply it" not in source
    assert "running poller does not hot-reload" not in source
