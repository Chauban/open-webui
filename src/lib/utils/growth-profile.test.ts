import { describe, expect, test } from 'vitest';

import { buildProfileQuery, buildTrendPath } from './growth-profile';

describe('growth profile filters', () => {
	test('serializes only explicit filters', () => {
		expect(
			buildProfileQuery({ start_at: 10, end_at: 20, assignment_id: 'assignment-1', round_no: 2 })
		).toBe('start_at=10&end_at=20&assignment_id=assignment-1&round_no=2');
		expect(buildProfileQuery({ assignment_id: undefined })).toBe('');
	});
});

describe('trend path', () => {
	const toX = (index: number) => index * 10;
	const toY = (value: number) => 100 - value;

	test('keeps a real zero and breaks the line at missing data', () => {
		const path = buildTrendPath([0, 10, null, 20], 4, 0, 100, toX, toY);
		expect(path).toBe('M0.00,100.00 L10.00,90.00 M30.00,80.00');
	});

	test('does not invent a path for entirely missing data', () => {
		expect(buildTrendPath([null, null], 2, 0, 100, toX, toY)).toBe('');
	});
});
