// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test } from 'vitest';
import WritingComposition from './WritingComposition.svelte';

afterEach(cleanup);
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);

test('updates composition and answered count without remounting', async () => {
	const { rerender } = render(WritingComposition, { props: {
		sourceRuns: [], clarificationAnsweredCount: 0
	}, context });
	expect(screen.getByText('Composition will appear as you write.')).toBeTruthy();
	await rerender({ sourceRuns: [
		{ startOffset: 0, endOffset: 4, sourceType: 'user_typed' },
		{ startOffset: 4, endOffset: 10, sourceType: 'ai_pasted' }
	], clarificationAnsweredCount: 2 });
	expect(screen.getByText('40%')).toBeTruthy();
	expect(screen.getByText('60%')).toBeTruthy();
	expect(screen.getByText('2')).toBeTruthy();
	expect(screen.queryByRole('alert')).toBeNull();
	await rerender({ sourceRuns: [], clarificationAnsweredCount: null });
	expect(screen.queryByText('60%')).toBeNull();
	expect(screen.getByText('—')).toBeTruthy();
});
