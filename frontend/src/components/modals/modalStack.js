const FOCUSABLE = "a[href],button,input,select,textarea,[tabindex],[contenteditable='true']";
const entries = [];
const snapshots = new Map();
let previousOverflow;
let observer;
let movingFocus = false;

function portalRoot(dialog) {
    let root = dialog;
    while (root?.parentElement && root.parentElement !== document.body) {
        root = root.parentElement;
    }
    if (root?.parentElement !== document.body) {
        throw new Error("A modal must be mounted in a body portal");
    }
    return root;
}

function remember(element) {
    if (!element || snapshots.has(element)) return;
    snapshots.set(element, {
        inert: element.inert,
        inertAttribute: element.getAttribute("inert"),
        ariaHidden: element.getAttribute("aria-hidden"),
    });
}

function restoreAttribute(element, name, value) {
    if (value === null) element.removeAttribute(name);
    else element.setAttribute(name, value);
}

function restore(element, state) {
    if (state.inert === undefined) delete element.inert;
    else element.inert = state.inert;
    restoreAttribute(element, "inert", state.inertAttribute);
    restoreAttribute(element, "aria-hidden", state.ariaHidden);
}

function isolate(element) {
    element.inert = true;
    element.setAttribute("inert", "");
    element.setAttribute("aria-hidden", "true");
}

function visible(element) {
    if (!(element instanceof HTMLElement) || !element.isConnected
        || element.matches(":disabled,input[type='hidden']")) {
        return false;
    }
    for (let parent = element; parent; parent = parent.parentElement) {
        if (parent.hidden || parent.inert || parent.hasAttribute("inert")
            || parent.getAttribute("aria-hidden") === "true") return false;
        const style = window.getComputedStyle(parent);
        if (style.display === "none" || ["hidden", "collapse"].includes(style.visibility)) return false;
    }
    return true;
}

function focusable(dialog) {
    return [...dialog.querySelectorAll(FOCUSABLE)]
        .filter((element) => element.tabIndex >= 0 && visible(element));
}

function focusInside(entry, requested) {
    const target = [requested, entry.initialFocus?.(), ...focusable(entry.dialog), entry.dialog]
        .find((element) => visible(element) && entry.dialog.contains(element));
    if (!target || movingFocus) return;
    movingFocus = true;
    try {
        target.focus({ preventScroll: true });
    } finally {
        movingFocus = false;
    }
}

function synchronize() {
    const top = entries.at(-1);
    if (!top) return;
    const children = [...document.body.children];
    children.forEach(remember);
    entries.forEach((entry) => remember(entry.background));
    snapshots.forEach((state, element) => restore(element, state));
    children.filter((element) => element !== top.root).forEach(isolate);
    entries.forEach(({ background }) => {
        if (background && !background.contains(top.dialog) && !top.root.contains(background)) {
            isolate(background);
        }
    });
    top.root.inert = false;
    top.root.removeAttribute("inert");
    top.root.removeAttribute("aria-hidden");
    document.body.style.overflow = "hidden";
}

function handleKeyDown(event) {
    const top = entries.at(-1);
    if (!top || event.defaultPrevented) return;
    if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        if (!top.closeBlocked()) top.onRequestClose?.();
        return;
    }
    if (event.key !== "Tab") return;
    const controls = focusable(top.dialog);
    const first = controls[0];
    const last = controls.at(-1);
    const active = document.activeElement;
    if (!controls.includes(active) || active === (event.shiftKey ? first : last)) {
        event.preventDefault();
        focusInside(top, event.shiftKey ? last : first);
    }
}

function handleFocusIn(event) {
    const top = entries.at(-1);
    if (top && !top.dialog.contains(event.target)) focusInside(top);
}

function release(entry) {
    const index = entries.indexOf(entry);
    if (index === -1) return;
    const wasTop = index === entries.length - 1;
    entries.splice(index, 1);
    const target = entry.returnFocus || entry.previouslyFocused;
    entries.forEach((remaining) => {
        if (entry.dialog.contains(remaining.previouslyFocused)) {
            remaining.previouslyFocused = target;
        }
    });
    const top = entries.at(-1);
    if (top) {
        synchronize();
        if (wasTop) focusInside(top, target);
        return;
    }
    observer.disconnect();
    observer = undefined;
    document.removeEventListener("keydown", handleKeyDown);
    document.removeEventListener("focusin", handleFocusIn);
    snapshots.forEach((state, element) => restore(element, state));
    snapshots.clear();
    document.body.style.overflow = previousOverflow;
    previousOverflow = undefined;
    const returnTarget = [entry.returnFocus, entry.previouslyFocused].find(visible);
    returnTarget?.focus({ preventScroll: true });
}

export function registerModal({
    dialog,
    initialFocus,
    onRequestClose,
    closeBlocked = () => false,
    returnFocus,
    background,
}) {
    const entry = {
        dialog,
        root: portalRoot(dialog),
        initialFocus,
        onRequestClose,
        closeBlocked,
        returnFocus: returnFocus instanceof HTMLElement ? returnFocus : null,
        background,
        previouslyFocused: document.activeElement,
    };
    if (!entries.length) {
        previousOverflow = document.body.style.overflow;
        observer = new MutationObserver(synchronize);
        observer.observe(document.body, { childList: true });
        document.addEventListener("keydown", handleKeyDown);
        document.addEventListener("focusin", handleFocusIn);
    }
    entries.push(entry);
    synchronize();
    focusInside(entry);
    return () => release(entry);
}
