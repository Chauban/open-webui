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
