// @vitest-environment jsdom

import { render } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { describe, expect, test } from 'vitest';

import EduTrendChart from './EduTrendChart.svelte';

const context = new Map([
	[
		'i18n',
		readable({
			t: (key: string) => key
		})
	]
]);

describe('EduTrendChart', () => {
	test('renders keyboard targets, full point labels, and a data-table control', () => {
		const { container } = render(EduTrendChart, {
			context,
			props: {
				labels: ['Essay · Round 1 · 9/1', 'Essay · Round 2 · 9/2'],
				axisLabels: ['9/1', '9/2'],
				series: [{ key: 'score', label: 'Score', values: [0, 80] }],
				min: 0,
				max: 100
			}
		});

		const body = container.innerHTML;
		expect(body).toContain('tabindex="0"');
		expect(body).toContain('role="button"');
		expect(body).toContain('role="group"');
		expect(body).toContain('r="22"');
		expect(body).toContain('Essay · Round 1 · 9/1');
		expect(body).toContain('Show data table');
		expect(body).toContain('9/1');
	});
});
