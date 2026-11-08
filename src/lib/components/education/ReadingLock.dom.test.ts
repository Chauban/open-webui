// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test } from 'vitest';
import ReadingLock from './ReadingLock.svelte';

afterEach(cleanup);
test('locks keyboard interaction with the draft and releases it when reading ends', async () => {
	const { container, rerender } = render(ReadingLock, {
		props: { locked: false },
		context: new Map([['i18n', readable({ t: (key: string) => key })]])
	});
	expect((container.firstElementChild?.firstElementChild as HTMLElement).inert).toBe(false);
	await rerender({ locked: true });
	expect((container.firstElementChild?.firstElementChild as HTMLElement).inert).toBe(true);
	expect(container.querySelector('[aria-busy="true"]')).toBeTruthy();
	expect(screen.getByRole('status').textContent).toContain('暂时无法编辑或提交');
	await rerender({ locked: false });
	expect((container.firstElementChild?.firstElementChild as HTMLElement).inert).toBe(false);
	expect(screen.queryByRole('status')).toBeNull();
});

test('keeps the draft locked without repeating progress already shown in chat', async () => {
	const { container, rerender } = render(ReadingLock, {
		props: { locked: true, showProgress: false },
		context: new Map([['i18n', readable({ t: (key: string) => key })]])
	});
	expect((container.firstElementChild?.firstElementChild as HTMLElement).inert).toBe(true);
	expect(container.querySelector('[aria-busy="true"]')).toBeTruthy();
	expect(container.querySelector('.absolute.inset-0')).toBeTruthy();
	expect(screen.queryByRole('status')).toBeNull();
	await rerender({ locked: true, showProgress: true });
	expect(screen.getAllByRole('status')).toHaveLength(1);
	await rerender({ locked: false, showProgress: false });
	expect((container.firstElementChild?.firstElementChild as HTMLElement).inert).toBe(false);
	expect(container.querySelector('.absolute.inset-0')).toBeNull();
});
