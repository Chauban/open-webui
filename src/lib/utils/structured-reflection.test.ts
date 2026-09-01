import { describe, expect, test } from 'vitest';

import { getStructuredReflectionError } from './structured-reflection';

const validReflection = {
	action: 'I replaced the weak claim with a specific evidence-based claim.',
	location: 'Paragraph 2',
	judgement: 'The new claim is supported by the source and answers the prompt.',
	next_step: 'Check the conclusion against the rubric.'
};

describe('structured reflection validation', () => {
	test('accepts four concrete evidence fields', () => {
		expect(getStructuredReflectionError(validReflection)).toBeNull();
	});

	test.each([
		['action', 'short', 'Describe what you changed in at least 10 characters.'],
		['location', 'x', 'Name where you made the change.'],
		['judgement', 'too short', 'Explain your judgement in at least 10 characters.'],
		['next_step', 'soon', 'Describe your next step in at least 5 characters.']
	] as const)('rejects an underspecified %s', (field, value, expected) => {
		expect(getStructuredReflectionError({ ...validReflection, [field]: value })).toBe(expected);
	});
});
