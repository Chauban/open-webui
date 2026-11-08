// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { readable, writable } from 'svelte/store';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { teachingApi } from '$lib/apis/education/teaching';
import { models } from '$lib/stores';
import TeachingModels from './TeachingModels.svelte';

vi.mock('$lib/apis/education/teaching', () => ({ teachingApi: vi.fn() }));
vi.mock('$lib/stores', () => ({ models: writable([]) }));

const publicGrant = { principal_type: 'user', principal_id: '*', permission: 'read' };
const publicModel = {
	id: 'public-model',
	name: '公开模型',
	owned_by: 'openai' as const,
	external: false,
	info: { is_active: true, access_grants: [publicGrant] }
};
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);

beforeEach(() => {
	vi.clearAllMocks();
	vi.mocked(teachingApi).mockResolvedValue({
		policy: { model_ids: ['public-model', 'private-model'], recommended_model_id: 'private-model' }
	});
});
afterEach(cleanup);

test('只展示已公开且启用的普通模型，不把个人或组共享当作公开', () => {
	const excluded = [
		{ id: 'private-model', info: { access_grants: [] } },
		{ id: 'unconfigured', info: undefined },
		{ id: 'shared-user', info: { access_grants: [{ ...publicGrant, principal_id: 'teacher' }] } },
		{ id: 'shared-group', info: { access_grants: [{ ...publicGrant, principal_type: 'group' }] } },
		{ id: 'write-only', info: { access_grants: [{ ...publicGrant, permission: 'write' }] } },
		{ id: 'disabled', info: { ...publicModel.info, is_active: false } },
		{ id: 'arena', owned_by: 'arena' },
		{ id: 'pipe', pipe: {} },
		{ id: 'pipeline', pipeline: {} }
	];
	models.set([
		publicModel,
		...excluded.map((model) => ({ ...publicModel, name: model.id, ...model }))
	] as any);
	render(TeachingModels, { context });
	expect(screen.getAllByRole('checkbox')).toHaveLength(1);
	expect(screen.getByRole('checkbox', { name: '公开模型' })).toBeTruthy();
});

test('推荐列表及保存内容排除非公开的已选项', async () => {
	models.set([publicModel] as any);
	render(TeachingModels, { context });
	await vi.waitFor(() => {
		expect((screen.getByRole('checkbox', { name: '公开模型' }) as HTMLInputElement).checked).toBe(
			true
		);
	});
	const select = screen.getByRole('combobox', { name: '推荐模型' }) as HTMLSelectElement;
	expect(select.value).toBe('');
	expect([...select.options].map((option) => option.value)).toEqual(['', 'public-model']);
	await fireEvent.change(select, { target: { value: 'public-model' } });
	await fireEvent.click(screen.getByRole('button', { name: '保存教学模型' }));
	expect(teachingApi).toHaveBeenLastCalledWith('/admin/teaching-models', 'PUT', {
		model_ids: ['public-model'],
		recommended_model_id: 'public-model'
	});

	models.set([{ ...publicModel, info: { is_active: true, access_grants: [] } }] as any);
	await vi.waitFor(() => expect(screen.queryByRole('checkbox')).toBeNull());
	expect(select.value).toBe('');
	await fireEvent.click(screen.getByRole('button', { name: '保存教学模型' }));
	expect(teachingApi).toHaveBeenLastCalledWith('/admin/teaching-models', 'PUT', {
		model_ids: [],
		recommended_model_id: null
	});
});

test('没有公开模型时说明应先到模型设置公开', () => {
	models.set([]);
	render(TeachingModels, { context });
	expect(screen.queryByRole('checkbox')).toBeNull();
	expect(
		screen.getByText('No public models available. Make a model public in Model Settings first.')
	).toBeTruthy();
});
