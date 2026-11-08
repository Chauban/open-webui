// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test } from 'vitest';
import FallbackModelSelect from './FallbackModelSelect.svelte';

afterEach(cleanup);
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);
const options = [
	{ id: 'gemini', name: 'Gemini', provider: 'primary.example', connection: 0 },
	{ id: 'another', name: 'Same provider', provider: 'primary.example', connection: 0 },
	{ id: 'google/gemini', name: 'Gemini', provider: 'backup.example', connection: 1 }
];

test('只显示其他连接，使用实际 ID 选择，已有配置可回显和清空', async () => {
	render(FallbackModelSelect, {
		props: { primaryId: 'gemini', value: 'google/gemini', options },
		context
	});
	const select = screen.getByRole('combobox', { name: '备用模型（可选）' }) as HTMLSelectElement;
	expect(select.value).toBe('google/gemini');
	expect(screen.queryByRole('option', { name: /Same provider/ })).toBeNull();
	expect(screen.getByRole('option', { name: /backup.example/ })).toBeTruthy();
	await fireEvent.change(select, { target: { value: '' } });
	expect(select.value).toBe('');
});

test('列表失败不清除原配置，并提示重新打开', () => {
	render(FallbackModelSelect, { props: { value: 'saved-model', unavailable: true }, context });
	expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('saved-model');
	expect(screen.getByRole('alert').textContent).toContain('加载失败');
});
