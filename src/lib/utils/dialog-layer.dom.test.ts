// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest';
import { dialogLayer, dismissTopDialog, hasOpenDialogs } from './dialog-layer';

const cleanups: (() => void)[] = [];
afterEach(() => {
	cleanups.reverse().forEach((destroy) => destroy());
	cleanups.length = 0;
});
function open(dismissible = true) {
	const overlay = document.createElement('div');
	overlay.innerHTML = '<div role="dialog" tabindex="-1"><button>Cancel</button></div>';
	const dismiss = vi.fn();
	const action = dialogLayer(overlay, { dismissible, onDismiss: dismiss });
	let active = true;
	const destroy = () => {
		if (active) action.destroy();
		active = false;
	};
	cleanups.push(destroy);
	return { overlay, dismiss, destroy, action };
}
test('Escape dismisses only the top layer and keeps scrolling locked until the last closes', () => {
	document.body.style.overflow = 'auto';
	const parent = open();
	const child = open();
	expect(hasOpenDialogs()).toBe(true);
	window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
	expect(child.dismiss).toHaveBeenCalledTimes(1);
	expect(parent.dismiss).not.toHaveBeenCalled();
	child.destroy();
	expect(document.body.style.overflow).toBe('hidden');
	window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
	expect(parent.dismiss).toHaveBeenCalledTimes(1);
	parent.destroy();
	expect(hasOpenDialogs()).toBe(false);
	expect(document.body.style.overflow).toBe('auto');
});
test('busy dialogs ignore backdrop and Escape; consumed Escape belongs to the child menu', () => {
	const layer = open(false);
	dismissTopDialog();
	layer.overlay.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
	window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
	expect(layer.dismiss).not.toHaveBeenCalled();
	layer.action.update({ dismissible: true, onDismiss: layer.dismiss });
	const consumed = new KeyboardEvent('keydown', { key: 'Escape', cancelable: true });
	consumed.preventDefault();
	window.dispatchEvent(consumed);
	expect(layer.dismiss).not.toHaveBeenCalled();
	layer.overlay.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
	expect(layer.dismiss).toHaveBeenCalledTimes(1);
});
