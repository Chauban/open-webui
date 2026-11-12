import { getWritingHome } from './index';
import { writable } from 'svelte/store';

export const writingHomeEvents = writable(0);
export const invalidateWritingHome = () => writingHomeEvents.update((value) => value + 1);

export const writingHomeIdentity = (user: any, token: string, origin = '') =>
	JSON.stringify([origin, token, user?.id, user?.role, user?.education_role, user?.classroom_id]);

/** No content cache: visibility/membership changes do not all have push events. */
export function createWritingHomeRequests(fetcher: (token: string) => Promise<any>) {
	let identity = '';
	let epoch = 0;
	let revision = 0;
	let flight: Promise<any> | null = null;
	let layout: { scope: string; expires: number; value: any } | null = null;
	return {
		invalidate() {
			revision++;
			layout = null;
		},
		reset() {
			identity = '';
			epoch++;
			flight = null;
			layout = null;
		},
		load(key: string, token: string): Promise<any> {
			if (key !== identity) {
				identity = key;
				epoch++;
				flight = null;
				layout = null;
			}
			if (flight) return flight;
			const generation = epoch;
			const request = (async () => {
				let data: any;
				let started: number;
				do {
					started = revision;
					data = await fetcher(token);
					if (generation !== epoch) return null;
				} while (started !== revision);
				return data;
			})();
			flight = request;
			void request
				.finally(() => {
					if (flight === request) flight = null;
				})
				.catch(() => {});
			return request;
		},
		remember(scope: string, value: any) {
			layout = { scope, value, expires: Date.now() + 15000 };
		},
		layout(scope: string) {
			return layout?.scope === scope && layout.expires > Date.now() ? layout.value : null;
		}
	};
}

export const writingHomeRequests = createWritingHomeRequests(getWritingHome);
