/** Discussion shortcuts preserve the student's unsent question and never submit it. */
export const appendDiscussionPrompt = (draft: string, reference: string) =>
	reference ? (draft.trim() ? `${draft}\n\n${reference}` : reference) : draft;
