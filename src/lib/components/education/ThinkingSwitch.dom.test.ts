// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test } from 'vitest';

import ThinkingSwitch from './ThinkingSwitch.svelte';

afterEach(cleanup);
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);

test('学生选的模型关不掉思考时不给开关,写明始终开着', () => {
	render(ThinkingSwitch, { props: { on: true, alwaysOn: true }, context });

	expect(screen.getByTestId('thinking-always-on').textContent).toBe('Always on for this model');
	expect(screen.queryByRole('switch')).toBeNull();
});

test('能关的模型照常给开关', () => {
	render(ThinkingSwitch, { props: { on: true }, context });

	expect(screen.queryByTestId('thinking-always-on')).toBeNull();
	expect(screen.getByRole('switch', { name: 'Deep thinking' })).toBeTruthy();
});
