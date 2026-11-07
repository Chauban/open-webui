// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test } from 'vitest';
import TeacherModelSummary from './TeacherModelSummary.svelte';
afterEach(cleanup);
const context = new Map([['i18n', readable({ t: (s: string) => s })]]);

test('汇总去重，保留各步骤实际模型；换轮次不遗留上一轮模型', async () => {
	const { rerender } = render(TeacherModelSummary, {
		props: {
			usage: [
				{ step: 'coaching_chat', models: ['deepseek-flash', 'another-model'] },
				{ step: 'first_read', models: ['deepseek-flash'] },
				{ step: 'reader_check', models: ['private-reader'] }
			]
		},
		context
	});
	expect(screen.getByText('deepseek-flash / another-model / private-reader')).toBeTruthy();
	expect(screen.getByText(/Coaching chat:/).textContent).toContain('another-model');
	expect(screen.getByText(/AI reader check:/).textContent).toContain('private-reader');
	await rerender({ usage: [{ step: 'coaching_chat', models: [null] }] });
	expect(screen.queryByText(/private-reader/)).toBeNull();
	expect(screen.getAllByText(/Model not recorded/).length).toBeGreaterThan(0);
});
