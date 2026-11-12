// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test } from 'vitest';
import AssignmentForm from './AssignmentForm.svelte';
import type { AssignmentDraft } from '$lib/utils/assignment-form';

afterEach(cleanup);
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);

test.each(['from_scratch', 'revise_draft', 'revise_argument'] as const)(
	'%s 已有提交后仍能修改评分方式、满分及维度，班级继续锁定',
	async (taskMode) => {
		const draft: AssignmentDraft = {
			taskMode,
			title: '测试作业',
			description: '',
			dueAt: '2030-01-01T12:00',
			photoTranscriptionEnabled: false,
			imageReadingEnabled: false,
			scoringMode: 'dimensions',
			scoreMax: '100',
			coachingStyle: 'socratic',
			challengeEnabled: false,
			challengeRounds: 2,
			challengeFocusKeys: [],
			reflectionQuestions: [],
			thinking: null,
			studentsChooseThinking: false,
			rubricCriteria: [
				{ key: 'ideas', label: '观点', maxScore: '60' },
				{ key: 'evidence', label: '证据', maxScore: '40' }
			]
		};
		const { container } = render(AssignmentForm, {
			props: { draft, hasSubmissions: true, taskModeLocked: true },
			context
		});
		expect(
			(container.querySelector('#assignment-basics select') as HTMLSelectElement).disabled
		).toBe(true);
		const scoring = within(container.querySelector('#assignment-scoring') as HTMLElement);
		expect((scoring.getByRole('combobox') as HTMLSelectElement).disabled).toBe(false);
		await fireEvent.input(scoring.getByDisplayValue('观点'), { target: { value: '论证质量' } });
		await fireEvent.input(scoring.getByDisplayValue('60'), { target: { value: '80' } });
		expect(scoring.getByDisplayValue('论证质量')).toBeTruthy();
		expect(scoring.getByDisplayValue('80')).toBeTruthy();
		expect(scoring.getByDisplayValue('120')).toBeTruthy();
		await fireEvent.click(scoring.getByRole('button', { name: 'Add Criterion' }));
		expect(scoring.getAllByPlaceholderText('Criterion label')).toHaveLength(3);
		await fireEvent.click(scoring.getAllByRole('button', { name: 'Remove' })[2]);
		expect(scoring.getAllByPlaceholderText('Criterion label')).toHaveLength(2);
		await fireEvent.change(scoring.getByRole('combobox'), { target: { value: 'total' } });
		const maximum = scoring.getByRole('spinbutton') as HTMLInputElement;
		expect(maximum.disabled).toBe(false);
		await fireEvent.input(maximum, { target: { value: '50' } });
		expect(maximum.value).toBe('50');
		expect(scoring.queryByPlaceholderText('Criterion label')).toBeNull();
	}
);

test.each(['from_scratch', 'revise_draft', 'revise_argument'] as const)(
	'%s 的 AI 辅导默认展开，折叠保留识图选择与反思题输入',
	async (taskMode) => {
		const draft: AssignmentDraft = {
			taskMode,
			photoTranscriptionEnabled: false,
			imageReadingEnabled: false,
			scoringMode: 'total',
			title: '',
			description: '',
			dueAt: '',
			scoreMax: '100',
			coachingStyle: 'socratic',
			challengeEnabled: false,
			challengeRounds: 2,
			challengeFocusKeys: [],
			reflectionQuestions: [
				{
					id: 'reflection',
					kind: 'text',
					prompt: '原有反思问题',
					required: true,
					options: [],
					allow_other: false,
					placeholder: null,
					show_when: 'always'
				}
			],
			rubricCriteria: [],
			thinking: null,
			studentsChooseThinking: false
		};
		const { container } = render(AssignmentForm, { props: { draft }, context });
		const aiButton = screen.getByRole('button', { name: /3 · AI Coaching/ });
		expect(aiButton.getAttribute('aria-expanded')).toBe('true');
		const imageSwitch = screen.getByRole('switch', {
			name: 'AI 读取参考图片'
		}) as HTMLInputElement;
		await fireEvent.click(imageSwitch);
		await fireEvent.click(aiButton);
		const panel = container.querySelector('#assignment-ai-content') as HTMLElement;
		expect(panel.hidden).toBe(true);
		expect(panel.inert).toBe(true);
		await fireEvent.click(aiButton);
		expect(panel.hidden).toBe(false);
		expect(screen.getByRole('switch', { name: 'AI 读取参考图片' })).toBe(imageSwitch);
		expect(imageSwitch.checked).toBe(true);

		const prompt = screen.getByDisplayValue('原有反思问题');
		await fireEvent.input(prompt, { target: { value: '已经修改的反思问题' } });
		const reflectionButton = screen.getByRole('button', { name: /Reflection Before Submitting/ });
		await fireEvent.click(reflectionButton);
		await fireEvent.click(reflectionButton);
		expect(screen.getByDisplayValue('已经修改的反思问题')).toBe(prompt);
	}
);
