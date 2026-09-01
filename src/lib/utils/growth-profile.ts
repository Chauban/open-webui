import type { StudentProfileFilters } from '$lib/apis/education/types';

export const buildProfileQuery = (filters: StudentProfileFilters = {}) => {
	const query = new URLSearchParams();
	Object.entries(filters).forEach(([key, value]) => {
		if (value !== undefined) query.set(key, `${value}`);
	});
	return query.toString();
};

export const buildTrendPath = (
	values: Array<number | null>,
	pointCount: number,
	low: number,
	high: number,
	toX: (index: number, count: number) => number,
	toY: (value: number, low: number, high: number) => number
) => {
	let path = '';
	let penDown = false;
	values.forEach((value, index) => {
		if (typeof value !== 'number') {
			penDown = false;
			return;
		}
		const command = penDown ? 'L' : 'M';
		path += `${command}${toX(index, pointCount).toFixed(2)},${toY(value, low, high).toFixed(2)} `;
		penDown = true;
	});
	return path.trim();
};
