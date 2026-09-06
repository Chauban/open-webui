// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test } from 'vitest';

import ChallengeSettings from './ChallengeSettings.svelte';

afterEach(cleanup);
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);

const criteria = [
	{ key: 'ideas', label: '立意' },
	{ key: 'structure', label: '结构' },
	{ key: 'evidence', label: '论据' }
];

test('没有评分维度时开关禁用', () => {
	render(ChallengeSettings, { props: { criteria: [], enabled: false }, context });

	const toggle = screen.getByRole('checkbox') as HTMLInputElement;
	expect(toggle.disabled).toBe(true);
	expect(screen.getByText('Add rubric criteria first, then you can turn on the read-through.'))
		.toBeTruthy();
});

test('焦点最多选两个，选满后其余维度不可点', async () => {
	render(ChallengeSettings, {
		props: { criteria, enabled: true, rounds: 3, focusKeys: [] },
		context
	});

	await fireEvent.click(screen.getByText('立意'));
	await fireEvent.click(screen.getByText('结构'));

	const third = screen.getByText('论据').closest('button') as HTMLButtonElement;
	expect(third.disabled).toBe(true);

	// 取消一个之后又能选了
	await fireEvent.click(screen.getByText('立意'));
	await waitFor(() =>
		expect((screen.getByText('论据').closest('button') as HTMLButtonElement).disabled).toBe(false)
	);
});

test('评分维度被删后残留的焦点自动剪掉', async () => {
	// 不剪的话保存会因为「焦点不在评分维度里」直接 422，教师看不懂那个报错。
	const { rerender } = render(ChallengeSettings, {
		props: { criteria, enabled: true, rounds: 3, focusKeys: ['evidence'] },
		context
	});
	expect(screen.queryByText('Pick at least one criterion for the reader to press on.')).toBeNull();

	// 「论据」这个维度被教师删掉了，原来选的焦点随之失效
	await rerender({
		criteria: [{ key: 'ideas', label: '立意' }],
		enabled: true,
		rounds: 3,
		focusKeys: ['evidence']
	});

	await waitFor(() =>
		expect(
			screen.getByText('Pick at least one criterion for the reader to press on.')
		).toBeTruthy()
	);
	expect(screen.queryByText('论据')).toBeNull();
});

test('一个焦点都没选时给出提示', () => {
	render(ChallengeSettings, {
		props: { criteria, enabled: true, rounds: 3, focusKeys: [] },
		context
	});

	expect(screen.getByText('Pick at least one criterion for the reader to press on.')).toBeTruthy();
});
