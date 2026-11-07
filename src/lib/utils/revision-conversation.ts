import type { RevisionReading } from '$lib/apis/education';

type ConversationMessage = {
	id: string;
	timestamp?: number;
	role?: string;
	content?: string;
	done?: boolean;
	error?: unknown;
	meta?: { education_context?: { source_text?: string; called_at?: number } };
};

/** Interleave immutable readings with the active chat branch, without creating fake chat messages. */
export const revisionTimeline = (messages: ConversationMessage[], readings: RevisionReading[]) => {
	const rows = [
		...messages.map((message, index) => ({
			kind: 'message' as const,
			key: `message:${message.id}`,
			time: message.timestamp ?? 0,
			index,
			message
		})),
		...readings.map((reading, index) => ({
			kind: 'reading' as const,
			key: `reading:${reading.id}`,
			time: reading.created_at,
			index,
			reading
		}))
	];
	if (readings.length === 0) return rows;
	return rows.sort(
		(a, b) =>
			a.time - b.time || (a.kind === b.kind ? a.index - b.index : a.kind === 'reading' ? -1 : 1)
	);
};

export const lastReadDraft = (
	messages: ConversationMessage[],
	readings: RevisionReading[],
	baseline: string
) => {
	const snapshots = [
		...readings
			.filter((r) => r.status === 'ready')
			.map((r) => ({ time: r.created_at, text: r.source_text })),
		...messages
			.filter(
				(m) =>
					m.role === 'assistant' &&
					Boolean(m.content?.trim()) &&
					m.done &&
					!m.error &&
					typeof m.meta?.education_context?.source_text === 'string'
			)
			.map((m) => ({
				time: m.meta!.education_context!.called_at ?? m.timestamp ?? 0,
				text: m.meta!.education_context!.source_text!
			}))
	];
	return snapshots.sort((a, b) => a.time - b.time).at(-1)?.text ?? baseline;
};
export const hasDraftChanges = (current: string, reviewed: string) =>
	current.replace(/\r\n/g, '\n').trim() !== reviewed.replace(/\r\n/g, '\n').trim();
export const revisionReviewPrompt = (explanation: string, request: string) =>
	explanation.trim() ? `${explanation.trim()}\n\n${request}` : request;
