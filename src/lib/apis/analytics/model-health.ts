import { WEBUI_API_BASE_URL } from '$lib/constants';

export type HealthPeriod = '1h' | '24h' | '7d';
export type ModelHealth = {
	model_id: string;
	calls: number;
	successes: number;
	failures: number;
	cancelled: number;
	fallback_calls: number;
	fallback_successes: number;
	average_duration_ms: number | null;
	affected_users: number;
	last_failure_at: number | null;
	failure_rate: number | null;
	attempts: number;
	attempt_failures: number;
	attempt_failure_rate: number | null;
	reasons: Record<string, number>;
	routes: {
		model_id: string;
		route: string;
		attempts: number;
		failures: number;
		cancelled: number;
		last_failure_at: number | null;
	}[];
};

export type ModelFailure = {
	id: string;
	call_id: string;
	model_id: string;
	requested_model: string;
	route: string;
	started_at: number;
	duration_ms: number;
	reason: string;
	http_status: number | null;
	fallback: boolean;
	final_outcome: string;
};

async function read<T>(token: string, path: string, params: URLSearchParams): Promise<T> {
	const response = await fetch(`${WEBUI_API_BASE_URL}/analytics/model-health${path}?${params}`, {
		headers: { authorization: `Bearer ${token}` }
	});
	if (!response.ok) throw new Error('Model health could not be loaded');
	return response.json();
}

export const getModelHealth = (token: string, period: HealthPeriod = '24h') =>
	read<{ models: ModelHealth[]; start: number; end: number }>(
		token,
		'',
		new URLSearchParams({ period })
	);

export const getModelFailures = (
	token: string,
	period: HealthPeriod,
	modelId: string,
	offset = 0
) =>
	read<{ items: ModelFailure[]; total: number }>(
		token,
		'/failures',
		new URLSearchParams({
			period,
			model_id: modelId,
			offset: String(offset),
			limit: '25'
		})
	);
