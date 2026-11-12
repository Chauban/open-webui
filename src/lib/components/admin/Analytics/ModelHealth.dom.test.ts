// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';
import ModelHealth from './ModelHealth.svelte';
import { getModelHealth, getModelFailures } from '$lib/apis/analytics/model-health';

vi.mock('$lib/apis/analytics/model-health', () => ({
	getModelHealth: vi.fn(),
	getModelFailures: vi.fn()
}));
vi.mock('$lib/stores', () => ({ models: readable([{ id: 'primary', name: 'Primary model' }]) }));
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);
afterEach(() => {
	cleanup();
	vi.resetAllMocks();
});

const row = {
	model_id: 'primary',
	calls: 4,
	successes: 2,
	failures: 1,
	cancelled: 1,
	fallback_calls: 1,
	fallback_successes: 1,
	average_duration_ms: 1000,
	affected_users: 1,
	last_failure_at: 1700000000,
	failure_rate: 1 / 3,
	attempts: 5,
	attempt_failures: 2,
	attempt_failure_rate: 0.5,
	reasons: { timeout: 2 },
	routes: [
		{
			model_id: 'primary',
			route: 'provider.test',
			attempts: 5,
			failures: 2,
			cancelled: 1,
			last_failure_at: 1700000000
		}
	]
};

test('shows separate rates, route failures and recovered final outcome', async () => {
	vi.mocked(getModelHealth).mockResolvedValue({ models: [row], start: 0, end: 1 });
	vi.mocked(getModelFailures).mockResolvedValue({
		items: [
			{
				id: 'a',
				call_id: 'c',
				model_id: 'primary',
				requested_model: 'primary',
				route: 'provider.test',
				started_at: 1700000000,
				duration_ms: 45000,
				reason: 'timeout',
				http_status: null,
				fallback: false,
				final_outcome: 'success'
			}
		],
		total: 1
	});
	render(ModelHealth, { context });
	expect(await screen.findByText('33.3%')).toBeTruthy();
	expect(screen.getByText('50.0%')).toBeTruthy();
	await fireEvent.click(screen.getByRole('button', { name: 'Primary model' }));
	expect(await screen.findByText('Succeeded after retry')).toBeTruthy();
	expect(screen.getByRole('link', { name: 'Model settings' }).getAttribute('href')).toBe(
		'/?settings=admin%3Amodels'
	);
	expect(getModelFailures).toHaveBeenCalledWith(localStorage.token, '24h', 'primary', 0);
});

test('distinguishes load failure from no data and allows refresh', async () => {
	vi.mocked(getModelHealth)
		.mockRejectedValueOnce(new Error('offline'))
		.mockResolvedValueOnce({ models: [], start: 0, end: 1 });
	render(ModelHealth, { context });
	expect(await screen.findByRole('alert')).toBeTruthy();
	await fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
	expect(
		await screen.findByText(
			'No completed model calls in this period. New calls will appear here after they finish.'
		)
	).toBeTruthy();
	expect(screen.queryByRole('alert')).toBeNull();
});

test('changing window discards stale responses', async () => {
	let resolveFirst: (value: any) => void = () => {};
	vi.mocked(getModelHealth)
		.mockImplementationOnce(
			() =>
				new Promise((resolve) => {
					resolveFirst = resolve;
				})
		)
		.mockResolvedValueOnce({ models: [], start: 0, end: 1 });
	render(ModelHealth, { context });
	await fireEvent.change(screen.getByRole('combobox', { name: 'Health time range' }), {
		target: { value: '1h' }
	});
	await screen.findByText(
		'No completed model calls in this period. New calls will appear here after they finish.'
	);
	resolveFirst({ models: [row], start: 0, end: 1 });
	await waitFor(() => expect(getModelHealth).toHaveBeenCalledTimes(2));
	expect(screen.queryByText('Primary model')).toBeNull();
});
