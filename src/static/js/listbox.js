/**
 * Popover listbox controls shared across pages.
 *
 * Interaction mirrors the dashboard filter menus: toggle on click, close on
 * outside click or Escape, arrow-key navigation, focus restore on close.
 */

function focusOption(menu, option) {
    const options = [...menu.querySelectorAll('[role="option"]')]
        .filter((item) => item instanceof HTMLButtonElement);
    options.forEach((item) => { item.tabIndex = item === option ? 0 : -1; });
    if (option) option.focus();
}

function createListbox({ trigger, menu, onSelect }) {
    let open = false;

    function setOpen(next, { restoreFocus = false } = {}) {
        open = next;
        trigger.setAttribute('aria-expanded', next ? 'true' : 'false');
        menu.classList.toggle('hidden', !next);
        if (next) {
            const selected = menu.querySelector('[role="option"][aria-selected="true"]');
            focusOption(menu, selected || menu.querySelector('[role="option"]'));
        } else if (restoreFocus) {
            trigger.focus();
        }
    }

    trigger.addEventListener('click', () => setOpen(!open));
    trigger.addEventListener('keydown', (event) => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            if (!open) setOpen(true);
        }
    });
    menu.addEventListener('keydown', (event) => {
        const options = [...menu.querySelectorAll('[role="option"]')]
            .filter((item) => item instanceof HTMLButtonElement);
        if (!options.length) return;
        const currentIndex = Math.max(0, options.indexOf(document.activeElement));
        let nextIndex = null;
        if (event.key === 'ArrowDown') nextIndex = (currentIndex + 1) % options.length;
        else if (event.key === 'ArrowUp') nextIndex = (currentIndex - 1 + options.length) % options.length;
        else if (event.key === 'Home') nextIndex = 0;
        else if (event.key === 'End') nextIndex = options.length - 1;
        else if (event.key === 'Escape') {
            event.preventDefault();
            setOpen(false, { restoreFocus: true });
            return;
        }
        if (nextIndex !== null) {
            event.preventDefault();
            focusOption(menu, options[nextIndex]);
        }
    });
    menu.addEventListener('click', (event) => {
        const option = event.target.closest('[role="option"]');
        if (!option) return;
        menu.querySelectorAll('[role="option"]').forEach((item) => {
            item.setAttribute('aria-selected', item === option ? 'true' : 'false');
        });
        setOpen(false, { restoreFocus: true });
        if (onSelect) onSelect(option);
    });
    document.addEventListener('click', (event) => {
        if (!open) return;
        if (trigger.contains(event.target) || menu.contains(event.target)) return;
        setOpen(false);
    });

    return {
        setOpen,
        get open() { return open; },
        setSelected(value) {
            menu.querySelectorAll('[role="option"]').forEach((item) => {
                item.setAttribute('aria-selected', item.dataset.value === value ? 'true' : 'false');
            });
        },
    };
}

function attachPopover({ trigger, panel }) {
    let open = false;

    function setOpen(next, { restoreFocus = false } = {}) {
        open = next;
        trigger.setAttribute('aria-expanded', next ? 'true' : 'false');
        panel.classList.toggle('hidden', !next);
        if (next) {
            const focusable = panel.querySelector('button, input');
            if (focusable) focusable.focus();
        } else if (restoreFocus) {
            trigger.focus();
        }
    }

    trigger.addEventListener('click', () => setOpen(!open));
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && open) setOpen(false, { restoreFocus: true });
    });
    document.addEventListener('click', (event) => {
        if (!open) return;
        if (trigger.contains(event.target) || panel.contains(event.target)) return;
        setOpen(false);
    });

    return { setOpen, get open() { return open; } };
}

export { createListbox, attachPopover };
