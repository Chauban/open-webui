import { WEBUI_API_BASE_URL } from '$lib/constants';
import type { ThinkingSetting, ReflectionQuestion } from './index';
import type { AssignmentDraft } from '$lib/utils/assignment-form';

export type AiCandidate = {
	prompt: string;
	model_id: string;
	thinking: ThinkingSetting;
	template_version: number;
	web_search?: boolean;
};
export type Preparation = {
	id: string;
	revision: number;
	assignment_id: string | null;
	base_config_revision: number | null;
	payload: { assignment: ReturnType<typeof preparationAssignment>; ai: AiCandidate };
	published: { assignment_ids: string[] } | null;
	coverage?: { stages: string[]; unavailable?: string };
	trials?: { id: string; created_at: number; sequence: number }[];
};
export type Trial = {
	id: string;
	preparation_id: string;
	sequence: number;
	config: { ai: AiCandidate; title: string; description: string };
	state: {
		baseline: string | null;
		draft: string;
		status: string;
		running_event_id: string | null;
		dialogue: { role: string; content: string }[];
		submission_preview?: { text: string; reflection_questions: ReflectionQuestion[] };
		evaluation?: { rating: string; notes: string };
	};
	events: {
		id: string;
		sequence: number;
		action: string;
		state: Trial['state'];
		call: Record<string, unknown> | null;
	}[];
};

export async function teachingApi<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
	const response = await fetch(`${WEBUI_API_BASE_URL}${path}`, {
		method,
		headers: { Authorization: `Bearer ${localStorage.token}`, 'Content-Type': 'application/json' },
		...(body === undefined ? {} : { body: JSON.stringify(body) })
	});
	if (!response.ok) throw await response.json();
	return response.json();
}

export async function trialAction(
	id: string,
	body: unknown,
	onDelta: (text: string) => void,
	signal?: AbortSignal
): Promise<void> {
	const response = await fetch(`${WEBUI_API_BASE_URL}/teacher/teaching-trials/${id}/actions`, {
		method: 'POST',
		headers: { Authorization: `Bearer ${localStorage.token}`, 'Content-Type': 'application/json' },
		body: JSON.stringify(body),
		signal
	});
	if (!response.ok) throw await response.json();
	if (!response.headers.get('content-type')?.includes('text/event-stream')) {
		await response.json();
		return;
	}
	const reader = response.body!.getReader();
	const decoder = new TextDecoder();
	let pending = '';
	let done = false;
	while (true) {
		const chunk = await reader.read();
		if (chunk.done) break;
		pending += decoder.decode(chunk.value, { stream: true });
		const lines = pending.split('\n');
		pending = lines.pop()!;
		for (const line of lines)
			if (line.startsWith('data:')) {
				const data = JSON.parse(line.slice(5));
				if (data.delta) onDelta(data.delta);
				if (data.done) done = true;
			}
	}
	if (!done) throw new Error('Generation interrupted. Your trial history has been retained.');
}

export function preparationAssignment(draft: AssignmentDraft, classrooms: string[]) {
	return {
		title: draft.title,
		description: draft.description,
		classroom_ids: classrooms,
		due_at: draft.dueAt ? Math.floor(new Date(draft.dueAt).getTime() / 1000) : null,
		score_max: Number(draft.scoreMax),
		coaching_style: draft.coachingStyle,
		task_mode: draft.taskMode,
		scoring_mode: draft.scoringMode,
		challenge_enabled: false,
		challenge_rounds: 3,
		challenge_focus_keys: [],
		reflection_questions: draft.reflectionQuestions,
		rubric_schema: {
			criteria:
				draft.scoringMode === 'total'
					? []
					: draft.rubricCriteria.map((c) => ({
							key: c.key,
							label: c.label,
							max_score: Number(c.maxScore)
						}))
		},
		model_params: { thinking: null, students_choose_thinking: false }
	};
}
