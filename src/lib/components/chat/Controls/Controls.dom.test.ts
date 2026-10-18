// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/svelte';
import { readable, writable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';

vi.mock('$lib/stores', () => ({
	config: readable({}),
	functions: readable([]),
	models: readable([]),
	settings: readable({}),
	showFileNavPath: writable(null),
	tools: readable([]),
	user: readable({
		role: 'user',
		permissions: { chat: { controls: true, valves: true, system_prompt: true, params: true } }
	})
}));
vi.mock('$lib/apis/tools', () => ({}));
vi.mock('$lib/apis/functions', () => ({}));

import Controls from './Controls.svelte';

afterEach(cleanup);
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);
const LOCK_NOTICE =
	'In assignment writing, the system prompt and model parameters follow your teacher’s instructions and the platform settings.';

test('有权限时显示系统提示与高级参数', () => {
	render(Controls, { props: { embed: true }, context });

	expect(screen.queryByText('System Prompt')).not.toBeNull();
	expect(screen.queryByText('Advanced Params')).not.toBeNull();
	expect(screen.queryByText(LOCK_NOTICE)).toBeNull();
});

test('作业写作区不显示这两栏,改为说明由老师和平台设定,其余照常', () => {
	render(Controls, { props: { embed: true, lockModelOverrides: true }, context });

	expect(screen.queryByText('System Prompt')).toBeNull();
	expect(screen.queryByText('Advanced Params')).toBeNull();
	expect(screen.queryByText(LOCK_NOTICE)).not.toBeNull();
	expect(screen.queryByText('Valves')).not.toBeNull();
});
