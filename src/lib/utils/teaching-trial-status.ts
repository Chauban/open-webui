import type { Trial } from '$lib/apis/education/teaching';

export type TrialOutcome = {
	status: 'idle' | 'running' | 'ready' | 'failed' | 'stopped';
	label: string;
	message: string;
};

const record = (value: unknown): Record<string, unknown> =>
	value !== null && typeof value === 'object' ? (value as Record<string, unknown>) : {};

/** Derive display state from persisted facts; never repair or rewrite trial evidence. */
export function teachingTrialStatus(trial: Trial): TrialOutcome {
	if (trial.state.running_event_id) return { status: 'running', label: '正在生成…', message: '' };
	const call = [...trial.events].reverse().find((event) => event.call)?.call;
	if (call?.status === 'failed') {
		const attempts = Array.isArray(call.attempts) ? call.attempts : [];
		const lastAttempt = record(attempts.at(-1));
		const outputs = Array.isArray(call.outputs) ? call.outputs : [];
		let message = '本次生成失败。可以重试，或换一个模型测试。';
		if (call.error_code === 'empty_response')
			message = '模型没有返回反馈正文。可以重试，或换一个模型测试。';
		else if (call.error_code === 'incomplete_response')
			message = '模型回复未完整生成。可以重试，或减少本次输出要求后重新测试。';
		else if (call.error_type === 'ValidationError' || record(outputs.at(-1)).valid === false)
			message = '模型已返回内容，但未通过初读格式检查。可以重试，或换一个模型测试。';
		else if (/Timeout/i.test(String(lastAttempt.error_type ?? call.error_type ?? '')))
			message = '模型服务响应超时，本次没有生成可用反馈。可以重试，或换一个模型测试。';
		return { status: 'failed', label: '生成失败', message };
	}
	if (call?.status === 'stopped')
		return {
			status: 'stopped',
			label: '已停止',
			message: '本次生成已停止，已完成的历史反馈保留。需要继续测试时，请在上方重新测试。'
		};
	if (call?.status === 'ready') return { status: 'ready', label: '已完成', message: '' };
	return { status: 'idle', label: '尚未开始', message: '' };
}
