/**
 * Shared fetch helper for all dashboard pages.
 *
 * Adds same-origin credentials, normalizes abort detection, and turns 401
 * responses into a `navidrome:unauthorized` event so pages can show login.
 */

export const UNAUTHORIZED_EVENT = 'navidrome:unauthorized';

export class UnauthorizedError extends Error {
    constructor() {
        super('unauthorized');
        this.name = 'UnauthorizedError';
    }
}

export function isAbortError(error) {
    return error instanceof DOMException && error.name === 'AbortError'
        || Boolean(error) && typeof error === 'object' && error.name === 'AbortError';
}

export async function apiFetch(url, options = {}) {
    const response = await fetch(url, { credentials: 'same-origin', ...options });
    if (response.status === 401) {
        window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
        throw new UnauthorizedError();
    }
    return response;
}
