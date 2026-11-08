// Keep progress visible while the long-running POST is pending. Stop also rejects late GETs.
export function pollReadingProgress<T>(load: () => Promise<T>, receive: (records: T) => void) {
	let stopped = false;
	let timer: ReturnType<typeof setTimeout>;
	const poll = async () => {
		try {
			const records = await load();
			if (!stopped) receive(records);
		} catch {
			// A temporary progress-read error must not interrupt the generation request.
		} finally {
			if (!stopped) timer = setTimeout(poll, 2000);
		}
	};
	timer = setTimeout(poll, 2000);
	return () => {
		stopped = true;
		clearTimeout(timer);
	};
}
