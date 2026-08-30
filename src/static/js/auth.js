/**
 * Login dialog controller shared by the dashboard and settings pages.
 *
 * Owns overlay visibility, background `inert`, focus save/restore and the
 * Tab focus trap. Pages keep their own markup; they pass element ids and the
 * submit callback.
 */

import { apiFetch, UnauthorizedError } from './http.js';

export function createLoginController({
    overlayId,
    tokenId,
    inertSelector,
    useHiddenClass = false,
    onAuthenticated,
    onShow = () => {},
    onHide = () => {},
}) {
    let lastFocus = null;

    const overlay = () => document.getElementById(overlayId);
    const tokenInput = () => document.getElementById(tokenId);
    const shell = () => document.querySelector(inertSelector);

    function isHidden() {
        return useHiddenClass
            ? overlay().classList.contains('hidden')
            : overlay().hidden;
    }

    function show(message) {
        if (isHidden()) lastFocus = document.activeElement;
        if (useHiddenClass) {
            overlay().classList.remove('hidden');
        } else {
            overlay().hidden = false;
        }
        shell().inert = true;
        setMessage(message || '');
        onShow();
        window.requestAnimationFrame(() => tokenInput().focus());
    }

    function hide() {
        if (useHiddenClass) {
            overlay().classList.add('hidden');
        } else {
            overlay().hidden = true;
        }
        shell().inert = false;
        setMessage('');
        onHide();
        if (lastFocus instanceof HTMLElement) lastFocus.focus();
        lastFocus = null;
    }

    function setMessage(text) {
        const errorEl = document.getElementById('loginError');
        if (!errorEl) return;
        if (text) {
            errorEl.textContent = text;
            errorEl.classList.remove('hidden');
            errorEl.hidden = false;
        } else {
            errorEl.classList.add('hidden');
            errorEl.hidden = true;
        }
    }

    function trapTab(event) {
        if (event.key !== 'Tab') return;
        const focusable = [...event.currentTarget.querySelectorAll('input, button')]
            .filter((element) => !element.disabled && !element.hidden);
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }

    async function submit(token) {
        const response = await apiFetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token }),
        }).catch((error) => {
            if (error instanceof UnauthorizedError) throw new Error('invalid token');
            throw error;
        });
        if (!response.ok) throw new Error('invalid token');
        hide();
        await onAuthenticated();
    }

    function bind() {
        overlay().addEventListener('keydown', trapTab);
    }

    return { show, hide, submit, bind, isHidden };
}
