import type { AiStepKey, RevisionReading } from '$lib/apis/education';

export type ReadingContext = {
	source_text?: string;
	called_at?: number;
	description_version?: number;
	teaching_version?: number;
	purpose?: string;
};
type Prompt = {
	id: string;
	role: string;
	content: unknown;
	created_at?: number;
	auto_started?: boolean;
	revision_review_requested?: boolean;
	thinking_level?: string | null;
	model_id?: string | null;
	education_context?: ReadingContext;
};
export type SourceSnapshot = {
	title: string;
	text: string;
	createdAt?: number;
	descriptionVersion?: number;
	teachingVersion?: number;
};
export type TeacherConversationEvent = {
	key: string;
	kind: 'prompt';
	role: string;
	label: string;
	meta: string;
	created_at: number;
	thinking_level: string | null;
	model_id: string | null;
	ai_step: AiStepKey | null;
	inserted_length: null;
	source: SourceSnapshot | null;
	run?: undefined;
};

export const teacherPromptLabel = (item: Prompt, t: (key: string) => string) => {
	if (item.role === 'user') {
		if (item.revision_review_requested)
			return t(item.auto_started ? '学生请求查看修改（快捷按钮）' : '学生说明并请求查看修改');
		return t(item.auto_started ? '平台预设消息' : 'Student');
	}
	return t(item.role === 'assistant' ? 'AI 回复' : 'System');
};

export const teacherConversationEvents = (
	prompts: Prompt[],
	readings: RevisionReading[],
	contexts: Array<ReadingContext & { message_id: string }>,
	t: (key: string) => string
): TeacherConversationEvent[] => {
	const byId = new Map(contexts.map((context) => [context.message_id, context]));
	const events: TeacherConversationEvent[] = prompts.map((item) => {
		const context = byId.get(item.id) ?? item.education_context;
		const meta = teacherPromptLabel(item, t);
		return {
			key: `prompt:${item.id}`,
			kind: 'prompt',
			role: item.role,
			label: typeof item.content === 'string' ? item.content : (JSON.stringify(item.content) ?? ''),
			meta,
			created_at: item.created_at ?? 0,
			thinking_level: item.thinking_level ?? null,
			model_id: item.role === 'assistant' ? (item.model_id ?? null) : null,
			ai_step: item.role === 'assistant' ? 'coaching_chat' : null,
			inserted_length: null,
			source:
				item.role === 'assistant' && typeof context?.source_text === 'string'
					? {
							title: meta,
							text: context.source_text,
							createdAt: context.called_at ?? item.created_at,
							descriptionVersion: context.description_version,
							teachingVersion: context.teaching_version
						}
					: null
		};
	});
	for (const record of readings) {
		if (!record.feedback) continue;
		const { understanding, strength, focus } = record.feedback;
		const label = [
			understanding,
			strength?.feedback,
			...focus.map((item) =>
				[item.quote ? `> ${item.quote.replaceAll('\n', '\n> ')}` : '', item.feedback]
					.filter(Boolean)
					.join('\n\n')
			)
		]
			.filter(Boolean)
			.join('\n\n');
		const meta = t(record.purpose === 'first_read' ? 'AI 初次阅读' : 'AI 阅读反馈');
		events.push({
			key: `reading:${record.id}`,
			kind: 'prompt',
			role: 'assistant',
			label,
			meta,
			created_at: record.created_at,
			thinking_level: record.thinking,
			model_id: record.model_id,
			ai_step: record.purpose,
			inserted_length: null,
			source: {
				title: meta,
				text: record.source_text,
				createdAt: record.created_at,
				descriptionVersion: record.context.description_version,
				teachingVersion: record.context.teaching_version
			}
		});
	}
	return events.sort(
		(a, b) =>
			a.created_at - b.created_at ||
			(a.key.startsWith('reading:') === b.key.startsWith('reading:')
				? 0
				: a.key.startsWith('reading:')
					? -1
					: 1)
	);
};

export type TeacherModelUsage = { step: AiStepKey; models: Array<string | null> };

/** Use only submitted evidence; never infer a past model from today's settings. */
export const teacherModelUsage = (
	events: TeacherConversationEvent[],
	steps: Array<{ step: AiStepKey; model_id: string }> = []
): TeacherModelUsage[] => {
	const groups = new Map<AiStepKey, Set<string | null>>();
	for (const item of [
		...events
			.filter((event) => event.role === 'assistant' && event.ai_step)
			.map((event) => ({ step: event.ai_step!, model_id: event.model_id })),
		...steps
	]) {
		const models = groups.get(item.step) ?? new Set<string | null>();
		models.add(item.model_id);
		groups.set(item.step, models);
	}
	return [...groups].map(([step, models]) => ({ step, models: [...models] }));
};
