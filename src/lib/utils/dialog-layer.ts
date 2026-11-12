import { createFocusTrap } from 'focus-trap';
import { v4 as uuidv4 } from 'uuid';

type DialogOptions = { dismissible: boolean; onDismiss: () => void };
const layers: HTMLElement[] = [];
const dismissers = new Map<HTMLElement, () => void>();
let originalOverflow = '';

export const hasOpenDialogs = () => layers.length > 0;
export function dismissTopDialog() {
	const top = layers[layers.length - 1];
	if (top) dismissers.get(top)?.();
}

/** One stack owns focus, Escape and scroll locking for all modal surfaces. */
export function dialogLayer(node: HTMLElement, options: DialogOptions) {
	const panel = node.querySelector<HTMLElement>('[role="dialog"]')!;
	const heading = panel.querySelector<HTMLElement>('.rw-dialog-heading');
	if (heading && !panel.hasAttribute('aria-labelledby')) {
		heading.id ||= `dialog-heading-${uuidv4()}`;
		panel.setAttribute('aria-labelledby', heading.id);
		panel.removeAttribute('aria-label');
	}
	if (!layers.length) {
		originalOverflow = document.body.style.overflow;
		document.body.style.overflow = 'hidden';
	}
	layers.push(node);
	// Portaled menus share this level: document order keeps the newest surface on top.
	node.style.zIndex = '9999';
	dismissers.set(node, () => {
		if (options.dismissible) options.onDismiss();
	});
	document.body.appendChild(node);
	const trap = createFocusTrap(panel, {
		initialFocus: () => panel.querySelector<HTMLElement>('[autofocus]') ?? panel,
		fallbackFocus: panel,
		escapeDeactivates: false,
		allowOutsideClick: true,
		preventScroll: true
	});
	trap.activate();
	const isTop = () => layers[layers.length - 1] === node;
	const keydown = (event: KeyboardEvent) => {
		if (event.key === 'Escape' && !event.defaultPrevented && isTop()) {
			event.stopImmediatePropagation();
			event.preventDefault();
			if (options.dismissible) options.onDismiss();
		}
	};
	// Menus and date pickers may portal next to the dialog rather than inside it.
	const pointerdown = (event: PointerEvent) => {
		if (!isTop() || !(event.target instanceof Element)) return;
		if (event.target === node) {
			if (options.dismissible) options.onDismiss();
		} else if (!node.contains(event.target)) {
			trap.pause();
		}
	};
	const focusin = () => {
		if (isTop()) trap.unpause();
	};
	window.addEventListener('keydown', keydown);
	document.addEventListener('pointerdown', pointerdown, true);
	panel.addEventListener('focusin', focusin);
	return {
		update(next: DialogOptions) {
			options = next;
		},
		destroy() {
			window.removeEventListener('keydown', keydown);
			document.removeEventListener('pointerdown', pointerdown, true);
			panel.removeEventListener('focusin', focusin);
			layers.splice(layers.indexOf(node), 1);
			dismissers.delete(node);
			trap.deactivate();
			node.remove();
			if (!layers.length) document.body.style.overflow = originalOverflow;
		}
	};
}
