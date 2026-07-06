type SaveOptions = {
	force?: boolean;
};

export const createSerializedSaveRunner = (
	save: (reason: string) => Promise<void>
): ((reason: string, options?: SaveOptions) => Promise<void>) => {
	let activeRun: Promise<void> | null = null;
	let queuedReason: string | null = null;

	const runLoop = async (reason: string): Promise<void> => {
		await save(reason);
		if (queuedReason) {
			const nextReason = queuedReason;
			queuedReason = null;
			await runLoop(nextReason);
		}
	};

	return async (reason: string, options: SaveOptions = {}) => {
		if (activeRun) {
			if (!options.force) {
				queuedReason = reason;
				return activeRun;
			}
			queuedReason = null;
			await activeRun;
		}

		activeRun = runLoop(reason).finally(() => {
			activeRun = null;
		});
		return activeRun;
	};
};
