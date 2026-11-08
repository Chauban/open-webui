// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';
import { getTeachingConfigs, saveTeachingConfig, type TeachingConfig } from '$lib/apis/education';
import TeachingTypes from './TeachingTypes.svelte';

vi.mock('$lib/apis/education', () => ({
	getTeachingConfigs: vi.fn(),
	saveTeachingConfig: vi.fn()
}));
vi.mock('svelte-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
afterEach(cleanup);

test('管理员通过单个辅导提示词编辑和保存教学标准与反馈方式', async () => {
	const config: TeachingConfig = {
		task_mode: 'from_scratch',
		version: 1,
		created_at: 1,
		prompt: '教学目标与判断标准\n论据支持观点。\n\n请用学生听得懂的话回应。',
		default_description: '',
		scoring_mode: 'total',
		score_max: 100,
		rubric_schema: { criteria: [] },
		reflection_questions: []
	};
	vi.mocked(getTeachingConfigs).mockResolvedValue({
		from_scratch: config,
		revise_draft: { ...config, task_mode: 'revise_draft' },
		revise_argument: { ...config, task_mode: 'revise_argument' }
	});
	vi.mocked(saveTeachingConfig).mockImplementation(async (_token, draft) => ({
		...draft,
		version: 2
	}));
	render(TeachingTypes, {
		context: new Map([['i18n', readable({ t: (key: string) => key })]])
	});
	const prompt = await screen.findByLabelText('辅导提示词');
	expect((prompt as HTMLTextAreaElement).value).toBe(config.prompt);
	expect(screen.queryByLabelText('教学目标与判断标准')).toBeNull();
	await fireEvent.input(prompt, { target: { value: '先解释判断依据，再提出一个具体动作。' } });
	await fireEvent.click(screen.getByRole('button', { name: '保存为新版本' }));
	await vi.waitFor(() => expect(saveTeachingConfig).toHaveBeenCalledOnce());
	const saved = vi.mocked(saveTeachingConfig).mock.calls[0][1];
	expect(saved.prompt).toBe('先解释判断依据，再提出一个具体动作。');
	expect(saved).not.toHaveProperty('standards');
});
