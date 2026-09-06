// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';

import ChallengeChecklist from './ChallengeChecklist.svelte';
import { updateChallengeChecklist } from '$lib/apis/education';

vi.mock('$lib/apis/education', () => ({
	updateChallengeChecklist: vi.fn()
}));

afterEach(cleanup);
beforeEach(() => {
	vi.clearAllMocks();
	// @ts-expect-error jsdom 里没有真实登录态，组件只把它当 bearer 透传。
	globalThis.localStorage.token = 'test-token';
});

const context = new Map([['i18n', readable({ t: (key: string) => key })]]);

const makeTurn = (turnNo: number, response: string | null) => ({
	id: `t-${turnNo}`,
	challenge_session_id: 'cs-1',
	turn_no: turnNo,
	focus_key: 'ideas',
	challenge_text: `这一点说服不了我 ${turnNo}`,
	quoted_span: `被质疑的第 ${turnNo} 句原文。`,
	response_text: response,
	responded_at: response ? 2 : null,
	created_at: 1
});

const detail = {
	session: {
		id: 'cs-1',
		writing_session_id: 'ws-1',
		assignment_id: 'a-1',
		student_id: 'u-1',
		submission_round_no: 1,
		source_version_id: 'v-1',
		focus_keys: ['ideas'],
		planned_rounds: 2,
		status: 'completed',
		closing_summary_json: { stood: [], unresolved: ['还缺一个反例', '数据来源没说'] },
		checklist_state_json: null,
		started_at: 1,
		ended_at: 3
	},
	turns: [makeTurn(1, '我补了一份调查数据。'), makeTurn(2, '我承认这里还缺一个反例。')]
} as never;

test('未解决条目回流成可勾选的待办', async () => {
	vi.mocked(updateChallengeChecklist).mockResolvedValue(detail);

	render(ChallengeChecklist, { props: { detail }, context });

	expect(screen.getByText('还缺一个反例')).toBeTruthy();
	expect(screen.getByText('数据来源没说')).toBeTruthy();

	await fireEvent.click(screen.getAllByRole('checkbox')[0]);
	await waitFor(() =>
		expect(updateChallengeChecklist).toHaveBeenCalledWith('test-token', 'cs-1', [0])
	);
});

test('关掉试读之后，学生仍能展开看到本轮完整往来', async () => {
	// 这一条是缺口本身：以前关掉对话框就只剩三条摘要，而真正要拿这份记录去改
	// 文章的是学生，教师端反倒一直有完整记录。
	render(ChallengeChecklist, { props: { detail }, context });

	// 默认折叠：清单才是拿来改文章的，回看是需要时才展开。
	expect(screen.queryByText('这一点说服不了我 1')).toBeNull();

	await fireEvent.click(screen.getByText('See what the reader asked'));

	expect(screen.getByText('这一点说服不了我 1')).toBeTruthy();
	expect(screen.getByText('这一点说服不了我 2')).toBeTruthy();
	expect(screen.getByText('我补了一份调查数据。')).toBeTruthy();
	// 被质疑的是哪一句，学生也要看得到。
	expect(screen.getByText('被质疑的第 1 句原文。')).toBeTruthy();
});

test('没有未解决条目时整块都不出现', () => {
	const clean = {
		...(detail as never as Record<string, unknown>),
		session: {
			...(detail as never as { session: Record<string, unknown> }).session,
			closing_summary_json: { stood: ['论点清楚'], unresolved: [] }
		}
	} as never;

	const { container } = render(ChallengeChecklist, { props: { detail: clean }, context });

	expect(container.textContent).not.toContain('From the read-through');
});
