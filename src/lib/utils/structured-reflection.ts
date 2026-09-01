export type StructuredReflectionDraft = {
	action: string;
	location: string;
	judgement: string;
	next_step: string;
};

export type StructuredReflectionError =
	| 'Describe what you changed in at least 10 characters.'
	| 'Name where you made the change.'
	| 'Explain your judgement in at least 10 characters.'
	| 'Describe your next step in at least 5 characters.';

export const getStructuredReflectionError = (
	reflection: StructuredReflectionDraft
): StructuredReflectionError | null => {
	if (reflection.action.trim().length < 10) {
		return 'Describe what you changed in at least 10 characters.';
	}
	if (reflection.location.trim().length < 2) {
		return 'Name where you made the change.';
	}
	if (reflection.judgement.trim().length < 10) {
		return 'Explain your judgement in at least 10 characters.';
	}
	if (reflection.next_step.trim().length < 5) {
		return 'Describe your next step in at least 5 characters.';
	}
	return null;
};
