const CONFIGURE_CATEGORIES = new Set([
    'unconfigured',
    'disabled',
    'auth_failed',
    'tls_error',
    'network_unreachable',
    'upstream_error',
    'invalid_response',
    'unknown',
]);

const KNOWN_CATEGORIES = new Set([
    ...CONFIGURE_CATEGORIES,
    'starting',
    'timeout',
    'collector_degraded',
    'connected_no_plays',
    'ready',
]);

function normalizedCategory(value) {
    return KNOWN_CATEGORIES.has(value) ? value : 'unknown';
}

export function connectionTestMessageKey(category, ok = false) {
    if (ok) return 'source.testSuccess';
    const normalized = category === 'incomplete' ? 'unconfigured' : normalizedCategory(category);
    return `source.diagnostics.${normalized}.title`;
}

export function createConnectionDiagnostics({ t, apiFetch, onConfigure }) {
    let snapshot = null;
    let mounted = false;

    function render() {
        if (!mounted) return;
        const card = document.getElementById('connectionGuidance');
        const category = normalizedCategory(snapshot?.category);
        card.dataset.category = category;
        card.hidden = category === 'ready';
        document.getElementById('connectionGuidanceTitle').textContent = t(
            `source.diagnostics.${category}.title`,
        );
        document.getElementById('connectionGuidanceDescription').textContent = t(
            `source.diagnostics.${category}.description`,
        );

        const facts = document.getElementById('connectionGuidanceFacts');
        facts.textContent = snapshot
            ? t('source.diagnostics.facts', {
                connections: snapshot.enabled_connection_count,
                records: snapshot.history_record_count,
            })
            : '';

        const action = document.getElementById('connectionGuidanceAction');
        const configure = CONFIGURE_CATEGORIES.has(category);
        action.textContent = t(
            configure ? 'source.diagnostics.configure' : 'source.diagnostics.refresh',
        );
        action.dataset.action = configure ? 'configure' : 'refresh';
    }

    async function load() {
        const response = await apiFetch('/api/diagnostics');
        if (!response.ok) throw new Error('diagnostics failed');
        snapshot = await response.json();
        render();
        return snapshot;
    }

    function mount() {
        if (mounted) return;
        mounted = true;
        document.getElementById('connectionGuidanceAction').addEventListener('click', async (event) => {
            if (event.currentTarget.dataset.action === 'configure') {
                onConfigure();
                return;
            }
            event.currentTarget.disabled = true;
            try {
                await load();
            } catch (_error) {
                // Authentication is handled globally; keep the last safe snapshot for other failures.
                render();
            } finally {
                event.currentTarget.disabled = false;
            }
        });
        render();
    }

    return {
        load,
        localize: render,
        mount,
    };
}
