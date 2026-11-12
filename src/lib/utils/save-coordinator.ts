type SaveOptions = {
	force?: boolean;
};

export const createSerializedSaveRunner = (
	save: (reason: string) => Promise<void>
): ((reason: string, options?: SaveOptions) => Promise<void>) => {
	let activeRun: Promise<void> | null = null;
	let queuedReason: string | null = null;

	const runLoop = async (reason: string): Promise<void> => {
		let next: string | null = reason;
		while (next !== null) {
			queuedReason = null;
			await save(next);
			next = queuedReason;
		}
	};

	return async (reason: string, _options: SaveOptions = {}) => {
		if (activeRun) {
			queuedReason = reason;
			return activeRun;
		}

		activeRun = runLoop(reason).finally(() => {
			activeRun = null;
		});
		return activeRun;
	};
};
