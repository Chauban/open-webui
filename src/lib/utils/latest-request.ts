export const createLatestRequestGate = () => {
	let current = 0;
	return {
		next: () => ++current,
		isLatest: (requestId: number) => requestId === current
	};
};
