// @vitest-environment jsdom
import { cleanup, render, screen, fireEvent } from '@testing-library/svelte';
import { readable, writable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';
import SelectorStub from './test-fixtures/ModelSelection.svelte';
vi.mock('./ModelSelector/Selector.svelte', () => ({ default: SelectorStub }));
vi.mock('$lib/stores', () => ({
	models: writable([]),
	pinnedModels: writable([]),
	settings: writable({}),
	user: writable(null)
}));
vi.mock('$lib/apis/users', () => ({ updateUserSettings: vi.fn() }));
import { models, user } from '$lib/stores';
import ModelSelector from './ModelSelector.svelte';
afterEach(cleanup);
const context = new Map([
	[
		'i18n',
		readable({
			t: (s: string, o = {}) =>
				Object.entries(o).reduce(
					(text, [key, value]) => text.replace(`{{${key}}}`, String(value)),
					s
				)
		})
	]
]);

test('单模型学生显示名称并选中；开放第二个模型后可以切换', async () => {
	user.set({ education_role: 'student', role: 'user' } as any);
	models.set([{ id: 'only', name: 'DeepSeek' }] as any);
	render(ModelSelector, { props: { selectedModels: ['removed'] }, context });
	expect(screen.getByTestId('single-student-model').textContent).toBe('DeepSeek');
	expect(screen.queryByRole('combobox')).toBeNull();
	models.set([
		{ id: 'only', name: 'DeepSeek' },
		{ id: 'second', name: 'Second' }
	] as any);
	const selector = (await screen.findByRole('combobox')) as HTMLSelectElement;
	expect(selector.value).toBe('only');
	expect(screen.queryByTestId('single-student-model')).toBeNull();
	await fireEvent.change(selector, { target: { value: 'second' } });
	expect(selector.value).toBe('second');
});

test('教师只有一个模型时仍保留选择控件', () => {
	user.set({ education_role: 'teacher', role: 'user' } as any);
	models.set([{ id: 'only', name: 'DeepSeek' }] as any);
	render(ModelSelector, { props: { selectedModels: ['only'] }, context });
	expect(screen.getByRole('combobox')).toBeTruthy();
	expect(screen.queryByTestId('single-student-model')).toBeNull();
});
