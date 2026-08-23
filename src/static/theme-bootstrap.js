        document.documentElement.dataset.theme =
            window.NavidromeI18n.readPreference('navidrome-theme', 'frappe');
        document.documentElement.dataset.motion =
            window.NavidromeI18n.readPreference('navidrome-motion', 'system') === 'reduced'
                ? 'reduced'
                : 'system';
