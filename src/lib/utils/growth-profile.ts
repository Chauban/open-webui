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

export type RubricDimension = {
	signature: string;
	key: string;
	label: string;
};

export const rubricDimensionSignature = (key: string, label: string) =>
	`${key}::${label.trim().toLocaleLowerCase().replace(/\s+/g, ' ')}`;

export const buildRubricDimensions = (
	points: Array<{ assignment_id: string; rubric: Record<string, number> | null }>,
	criteriaByAssignment: Record<
		string,
		Record<string, { key: string; label: string; max_score: number }>
	>
): RubricDimension[] => {
	const dimensions = new Map<string, RubricDimension>();
	for (const point of points) {
		for (const key of Object.keys(point.rubric ?? {})) {
			const criterion = criteriaByAssignment[point.assignment_id]?.[key];
			if (!criterion) continue;
			const signature = rubricDimensionSignature(key, criterion.label);
			dimensions.set(signature, { signature, key, label: criterion.label });
		}
	}
	return [...dimensions.values()];
};
