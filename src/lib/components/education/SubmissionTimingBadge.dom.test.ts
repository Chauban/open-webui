// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test } from 'vitest';
import SubmissionTimingBadge from './SubmissionTimingBadge.svelte';

afterEach(cleanup);
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);

test('shows a rose late label with the frozen deadline and removes it for on-time work', async () => {
	const view = render(SubmissionTimingBadge, {
		props: { timing: { effective_due_at: 1, is_late: true } },
		context
	});
	const badge = screen.getByText('Late submission');
	expect(badge.className).toContain('text-rose-700');
	expect(badge.getAttribute('title')).toContain('Deadline at submission');
	await view.rerender({ timing: { effective_due_at: 1, is_late: false } });
	expect(screen.queryByText('Late submission')).toBeNull();
});
