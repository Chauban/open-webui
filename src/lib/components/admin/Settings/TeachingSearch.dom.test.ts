// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';
import TeachingSearch from './TeachingSearch.svelte';
const api = vi.hoisted(() => vi.fn());
vi.mock('$lib/apis/education/teaching', () => ({ teachingApi: api }));
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);
afterEach(cleanup);

test('管理员仅保存开关与连接编号，不收集或发送密钥', async () => {
	api.mockImplementation(async (_path, method, body) =>
		method === 'PUT'
			? body
			: {
					policy: { enabled: false, connection_index: null },
					connections: [{ index: 2, name: 'DeepSeek · 3', has_key: true }]
				}
	);
	render(TeachingSearch, { context });
	await screen.findByRole('option', { name: 'DeepSeek · 3' });
	await fireEvent.click(screen.getByRole('checkbox', { name: '允许教师开启资料搜索' }));
	await fireEvent.change(screen.getByRole('combobox', { name: '搜索服务连接' }), {
		target: { value: '2' }
	});
	await fireEvent.click(screen.getByRole('button', { name: '保存资料搜索设置' }));
	await screen.findByText('已保存');
	expect(api).toHaveBeenLastCalledWith('/admin/teaching-search', 'PUT', {
		enabled: true,
		connection_index: 2
	});
	expect(screen.queryByRole('textbox')).toBeNull();
});
