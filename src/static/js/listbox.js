/**
 * Popover listbox controls shared across pages.
 *
 * Interaction: toggle on click, close on outside click, Escape, or Tab,
 * arrow-key navigation with wrap-around from a lost-focus state, and focus
 * restore on close. `onSelect` may return `false` to keep the popover open
 * (for example when an option reveals a sub-panel). Instances expose
 * `destroy()` for explicit listener teardown.
 */

function optionButtons(container) {
    return [...container.querySelectorAll('[role="option"]')]
        .filter((item) => item instanceof HTMLButtonElement);
}

function focusOption(menu, option) {
    const options = optionButtons(menu);
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

    function onTriggerClick() { setOpen(!open); }

    function onTriggerKeydown(event) {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            if (!open) setOpen(true);
        }
    }

    // Keyboard handling binds to the listbox element so sibling panels inside
    // the same popover (for example a custom date-range form) keep normal key
    // behavior in their inputs.
    const listbox = menu.querySelector('[role="listbox"]') || menu;

    function onListboxKeydown(event) {
        const options = optionButtons(listbox);
        if (!options.length) return;
        const currentIndex = options.indexOf(document.activeElement);
        let nextIndex = null;
        if (event.key === 'ArrowDown') nextIndex = currentIndex < 0 ? 0 : (currentIndex + 1) % options.length;
        else if (event.key === 'ArrowUp') nextIndex = currentIndex < 0 ? options.length - 1 : (currentIndex - 1 + options.length) % options.length;
        else if (event.key === 'Home') nextIndex = 0;
        else if (event.key === 'End') nextIndex = options.length - 1;
        else if (event.key === 'Escape' || event.key === 'Tab') {
            setOpen(false, { restoreFocus: event.key === 'Escape' });
            return;
        }
        if (nextIndex !== null) {
            event.preventDefault();
            focusOption(listbox, options[nextIndex]);
        }
    }

    function onMenuClick(event) {
        if (!(event.target instanceof Element)) return;
        const option = event.target.closest('[role="option"]');
        if (!option) return;
        if (onSelect && onSelect(option) === false) return;
        listbox.querySelectorAll('[role="option"]').forEach((item) => {
            item.setAttribute('aria-selected', item === option ? 'true' : 'false');
        });
        setOpen(false, { restoreFocus: true });
    }

    function onDocumentClick(event) {
        if (!open) return;
        if (trigger.contains(event.target) || menu.contains(event.target)) return;
        setOpen(false);
    }

    // Escape closes from anywhere inside the popover, including sibling
    // panels whose inputs handle their own keys.
    function onDocumentKeydown(event) {
        if (event.key !== 'Escape' || !open) return;
        if (listbox.contains(document.activeElement)) return;
        setOpen(false, { restoreFocus: true });
    }

    function onMenuFocusout(event) {
        if (!open) return;
        if (event.relatedTarget instanceof Node && menu.contains(event.relatedTarget)) return;
        setOpen(false);
    }

    trigger.addEventListener('click', onTriggerClick);
    trigger.addEventListener('keydown', onTriggerKeydown);
    listbox.addEventListener('keydown', onListboxKeydown);
    listbox.addEventListener('focusout', onMenuFocusout);
    menu.addEventListener('click', onMenuClick);
    document.addEventListener('click', onDocumentClick);
    document.addEventListener('keydown', onDocumentKeydown);

    return {
        setOpen,
        get open() { return open; },
        setSelected(value) {
            menu.querySelectorAll('[role="option"]').forEach((item) => {
                item.setAttribute('aria-selected', item.dataset.value === value ? 'true' : 'false');
            });
        },
        destroy() {
            trigger.removeEventListener('click', onTriggerClick);
            trigger.removeEventListener('keydown', onTriggerKeydown);
            listbox.removeEventListener('keydown', onListboxKeydown);
            listbox.removeEventListener('focusout', onMenuFocusout);
            menu.removeEventListener('click', onMenuClick);
            document.removeEventListener('click', onDocumentClick);
            document.removeEventListener('keydown', onDocumentKeydown);
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

    function onTriggerClick() { setOpen(!open); }

    function onDocumentKeydown(event) {
        if (event.key === 'Escape' && open) setOpen(false, { restoreFocus: true });
    }

    function onDocumentClick(event) {
        if (!open) return;
        if (trigger.contains(event.target) || panel.contains(event.target)) return;
        setOpen(false);
    }

    function onPanelFocusout(event) {
        if (!open) return;
        if (event.relatedTarget instanceof Node && panel.contains(event.relatedTarget)) return;
        setOpen(false);
    }

    trigger.addEventListener('click', onTriggerClick);
    document.addEventListener('keydown', onDocumentKeydown);
    document.addEventListener('click', onDocumentClick);
    panel.addEventListener('focusout', onPanelFocusout);

    return {
        setOpen,
        get open() { return open; },
        destroy() {
            trigger.removeEventListener('click', onTriggerClick);
            document.removeEventListener('keydown', onDocumentKeydown);
            document.removeEventListener('click', onDocumentClick);
            panel.removeEventListener('focusout', onPanelFocusout);
        },
    };
}

export { createListbox, attachPopover };
