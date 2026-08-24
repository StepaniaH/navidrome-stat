/**
 * Local display preferences shared by every page.
 *
 * Values live in localStorage; `onPreferenceChange` also fires for other
 * tabs through the `storage` event.
 */

function readPreference(key, fallback = null) {
    try {
        const value = window.localStorage.getItem(key);
        return value === null ? fallback : value;
    } catch (_error) {
        return fallback;
    }
}

function writePreference(key, value) {
    try {
        window.localStorage.setItem(key, value);
        return true;
    } catch (_error) {
        return false;
    }
}

function removePreference(key) {
    try {
        window.localStorage.removeItem(key);
        return true;
    } catch (_error) {
        return false;
    }
}

function onPreferenceChange(key, callback) {
    window.addEventListener('storage', (event) => {
        if (event.key === key) callback(event.newValue);
    });
}

export { readPreference, writePreference, removePreference, onPreferenceChange };
