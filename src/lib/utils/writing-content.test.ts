import { describe, expect, test } from 'vitest';

import { prepareAssistantContentForWriting } from './writing-content';

describe('prepareAssistantContentForWriting', () => {
	test('removes hidden reasoning and prepares visible markdown for rich-text insertion', () => {
		const result = prepareAssistantContentForWriting({
			content: `<details type="reasoning">
<summary>Thought for 2 seconds</summary>
Do not insert this.
</details>

# Final Answer

Use **clear evidence**:

- First point
- Second point`,
			modelName: 'Tutor',
			userName: 'Student'
		});

		expect(result.html).toContain('<h1>Final Answer</h1>');
		expect(result.html).toContain('<strong>clear evidence</strong>');
		expect(result.html).toContain('<li>First point</li>');
		expect(result.html).not.toContain('Do not insert this');
		expect(result.html).not.toContain('**clear evidence**');
		expect(result.html).not.toContain('<details');

		expect(result.text).toBe('Final Answer\nUse clear evidence:\nFirst point\nSecond point');
	});

	test('removes raw reasoning tags before insertion', () => {
		const result = prepareAssistantContentForWriting({
			content: `<think>private chain of thought</think>
<thinking>private scratchpad</thinking>
<reasoning>private rationale</reasoning>

Visible **answer**.`
		});

		expect(result.html).toContain('<strong>answer</strong>');
		expect(result.html).not.toContain('private chain of thought');
		expect(result.html).not.toContain('private scratchpad');
		expect(result.html).not.toContain('private rationale');
		expect(result.text).toBe('Visible answer.');
	});
});
