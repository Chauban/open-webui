// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';
import ConfirmDialog from './ConfirmDialog.svelte';

const context = new Map([['i18n', readable({ t: (key: string) => key })]]);
afterEach(cleanup);

test('component confirmation waits for an explicit decision and cancels when unmounted', async () => {
	const { component, unmount } = render(ConfirmDialog, { context });
	const decision = component.ask({
		title: 'Replace draft?',
		message: 'Current text will be replaced.'
	});
	const dialog = await screen.findByRole('dialog', { name: 'Replace draft?' });
	await fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
	expect(await decision).toBe(false);
	const next = component.ask({
		title: 'Replace draft?',
		message: 'Current text will be replaced.'
	});
	await screen.findByRole('dialog');
	unmount();
	expect(await next).toBe(false);
});

test('confirmation keeps a failed operation open and prevents duplicate submissions', async () => {
	let reject!: (error: Error) => void;
	const onConfirm = vi.fn(
		() =>
			new Promise<void>((_, fail) => {
				reject = fail;
			})
	);
	render(ConfirmDialog, { context, props: { show: true, title: 'Delete draft?', onConfirm } });
	await fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
	expect(
		(screen.getByRole('button', { name: 'Processing...' }) as HTMLButtonElement).disabled
	).toBe(true);
	await fireEvent.keyDown(window, { key: 'Escape' });
	expect(screen.getByRole('dialog')).toBeTruthy();
	reject(new Error('Could not save. Try again.'));
	await screen.findByRole('alert');
	expect(screen.getByRole('dialog')).toBeTruthy();
	expect(onConfirm).toHaveBeenCalledTimes(1);
	onConfirm.mockResolvedValueOnce();
	await fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
	await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
});
