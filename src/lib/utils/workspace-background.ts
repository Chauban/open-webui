/** Bound optional workspace work so it cannot fill every HTTP/1.1 connection.
 * This queues requests, never caches their results. Disposed consumers skip jobs
 * which have not started; each caller also guards its own late response.
 */
let tail: Promise<unknown> = Promise.resolve();
const flights = new Map<string, { promise: Promise<any>; current: () => boolean }>();

export function workspaceBackground<T>(key: string, run: () => Promise<T>, current: () => boolean) {
	const existing = flights.get(key);
	if (existing?.current()) return existing.promise as Promise<T | undefined>;
	const result = tail.catch(() => {}).then(() => (current() ? run() : undefined));
	flights.set(key, { promise: result, current });
	tail = result;
	void result
		.finally(() => {
			if (flights.get(key)?.promise === result) flights.delete(key);
		})
		.catch(() => {});
	return result;
}
