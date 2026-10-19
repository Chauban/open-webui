// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';

import type { RetryScope } from '$lib/apis/education';
import EducationAutoRetrySettings from './EducationAutoRetrySettings.svelte';

afterEach(cleanup);
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);

const SCOPES: RetryScope[] = [
	{ key: 'assignment_chat', admin_toggle: false },
	{ key: 'platform_steps', admin_toggle: false },
	{ key: 'personal_writing', admin_toggle: true }
];

test('按后端登记生成:始终重发的写明,个人写作给开关并保存', async () => {
	const onChange = vi.fn();
	render(EducationAutoRetrySettings, {
		props: { scopes: SCOPES, policy: { personal_writing: false }, onChange },
		context
	});

	expect(screen.getByTestId('auto-retry-assignment_chat').textContent).toContain('Always on');
	expect(screen.getByTestId('auto-retry-platform_steps').textContent).toContain('Always on');
	const toggle = screen.getByRole('switch', { name: 'Personal writing coaching chat' });
	expect(toggle.getAttribute('aria-checked')).toBe('false');

	await fireEvent.click(toggle);
	await vi.waitFor(() => expect(onChange).toHaveBeenCalledWith({ personal_writing: true }));
});
