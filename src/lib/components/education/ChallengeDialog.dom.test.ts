// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';

import ChallengeDialog from './ChallengeDialog.svelte';
import {
	respondToChallenge,
	skipAssignmentChallenge,
	skipAssignmentChallengeBeforeStart,
	startAssignmentChallenge
} from '$lib/apis/education';

vi.mock('$lib/apis/education', () => ({
	startAssignmentChallenge: vi.fn(),
	respondToChallenge: vi.fn(),
	skipAssignmentChallenge: vi.fn(),
	skipAssignmentChallengeBeforeStart: vi.fn()
}));

afterEach(cleanup);
beforeEach(() => {
	vi.clearAllMocks();
	// @ts-expect-error jsdom 里没有真实登录态，组件只把它当 bearer 透传。
	globalThis.localStorage.token = 'test-token';
});

const context = new Map([['i18n', readable({ t: (key: string) => key })]]);
const assignment = { id: 'a-1', title: 'Essay', challenge_rounds: 2 };

const makeSession = (overrides = {}) => ({
	id: 'cs-1',
	writing_session_id: 'ws-1',
	assignment_id: 'a-1',
	student_id: 'u-1',
	submission_round_no: 1,
	source_version_id: 'v-1',
	focus_keys: ['ideas'],
	planned_rounds: 2,
	status: 'in_progress',
	closing_summary_json: null,
	checklist_state_json: null,
	started_at: 1,
	ended_at: null,
	...overrides
});

const makeTurn = (turnNo: number, response: string | null = null) => ({
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

const baseProps = {
	assignment,
	writingSessionId: 'ws-1',
	modelId: 'test-model',
	onBackToRevise: () => {},
	onContinue: () => {}
};

test('契约先亮出来，再进第一轮质疑', async () => {
	vi.mocked(startAssignmentChallenge).mockResolvedValue({
		session: makeSession(),
		turns: [makeTurn(1)]
	} as never);

	render(ChallengeDialog, { props: { ...baseProps, detail: null }, context });

	// 不先讲清契约，学生会一直向它求助然后判定这 AI 很笨。
	expect(screen.getByText('I am a reader who does not agree with you.')).toBeTruthy();
	expect(
		screen.getByText(
			'I will not rewrite anything for you. I will only say where you have not convinced me.'
		)
	).toBeTruthy();
	// 入口措辞不出现「对抗 / 挑战」这类会让学生进入防御姿态的词。
	expect(screen.getByText('A reader takes a look first')).toBeTruthy();

	await fireEvent.click(screen.getByText('Start'));

	await waitFor(() => expect(screen.getByText('这一点说服不了我 1')).toBeTruthy());
	expect(startAssignmentChallenge).toHaveBeenCalledWith('test-token', 'a-1', {
		writing_session_id: 'ws-1',
		model: 'test-model'
	});
});

test('没写回应就不能进下一轮', async () => {
	render(ChallengeDialog, {
		props: { ...baseProps, detail: { session: makeSession(), turns: [makeTurn(1)] } },
		context
	});

	const send = screen.getByText('Send response').closest('button') as HTMLButtonElement;
	expect(send.disabled).toBe(true);

	await fireEvent.input(
		screen.getByPlaceholderText(
			'Answer in your own words. This reader will not write it for you.'
		),
		{ target: { value: '我补了一份调查数据。' } }
	);

	expect(send.disabled).toBe(false);
	expect(respondToChallenge).not.toHaveBeenCalled();
});

test('答满最后一轮后出现收尾清单和两个出口', async () => {
	vi.mocked(respondToChallenge).mockResolvedValue({
		session: makeSession({
			status: 'completed',
			ended_at: 9,
			closing_summary_json: { stood: ['论点说清了'], unresolved: ['还缺一个反例'] }
		}),
		turns: [makeTurn(1, '答1'), makeTurn(2, '答2')]
	} as never);

	render(ChallengeDialog, {
		props: {
			...baseProps,
			detail: { session: makeSession(), turns: [makeTurn(1, '答1'), makeTurn(2)] }
		},
		context
	});

	await fireEvent.input(
		screen.getByPlaceholderText(
			'Answer in your own words. This reader will not write it for you.'
		),
		{ target: { value: '我承认这里还缺一个反例。' } }
	);
	await fireEvent.click(screen.getByText('Send response'));

	await waitFor(() => expect(screen.getByText('还缺一个反例')).toBeTruthy());
	expect(screen.getByText('论点说清了')).toBeTruthy();
	// 收尾必须是正面的，而且要能带走：没有「回去修改」这个出口，质疑作用不到正文。
	expect(screen.getByText('Back to revise')).toBeTruthy();
	expect(screen.getByText('Continue to submit')).toBeTruthy();
	expect(respondToChallenge).toHaveBeenCalledWith('test-token', 'cs-1', {
		turn_no: 2,
		response_text: '我承认这里还缺一个反例。',
		model: 'test-model'
	});
});

test('跳过会留痕并直接进提交', async () => {
	vi.mocked(skipAssignmentChallenge).mockResolvedValue({
		session: makeSession({ status: 'skipped', ended_at: 9 }),
		turns: [makeTurn(1)]
	} as never);
	const onContinue = vi.fn();

	render(ChallengeDialog, {
		props: {
			...baseProps,
			onContinue,
			detail: { session: makeSession(), turns: [makeTurn(1)] }
		},
		context
	});

	await fireEvent.click(screen.getByText('Skip this time'));

	await waitFor(() => expect(onContinue).toHaveBeenCalled());
	expect(skipAssignmentChallenge).toHaveBeenCalledWith('test-token', 'cs-1');
});

test('契约页还没开始就跳过，同样要留痕', async () => {
	// 连开都不开的那批学生才是最该被教师看到的，不落库的话他们反而完全空白。
	vi.mocked(skipAssignmentChallengeBeforeStart).mockResolvedValue({
		session: makeSession({ status: 'skipped', ended_at: 3 }),
		turns: []
	} as never);

	const onContinue = vi.fn();
	render(ChallengeDialog, { props: { ...baseProps, onContinue, detail: null }, context });

	await fireEvent.click(screen.getByText('Skip this time'));

	await waitFor(() => expect(onContinue).toHaveBeenCalled());
	expect(skipAssignmentChallengeBeforeStart).toHaveBeenCalledWith(
		'test-token',
		'a-1',
		'ws-1'
	);
	// 没有 session 时不能走要 session id 的那个端点。
	expect(skipAssignmentChallenge).not.toHaveBeenCalled();
});
