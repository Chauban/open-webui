import { teachingApi, type Preparation } from '$lib/apis/education/teaching';

export type DraftBackup = {
	id: string;
	assignmentId: string | null;
	preparation: Preparation | null;
	payload: Preparation['payload'];
	updatedAt: number;
	creationSnapshot?: string;
	uncertain?: { snapshot: string; revision: number };
};
export type SaveState = 'idle' | 'saving' | 'saved' | 'failed' | 'conflict';
const prefix = (owner: string) => `assignment-drafts:${owner}:`;
const key = (owner: string, id: string) => `${prefix(owner)}${id}`;

export function localDrafts(owner: string): DraftBackup[] {
	const result: DraftBackup[] = [];
	for (let i = 0; i < localStorage.length; i++) {
		const name = localStorage.key(i)!;
		if (!name.startsWith(prefix(owner))) continue;
		try {
			const value = JSON.parse(localStorage.getItem(name)!);
			if (value.id && value.payload?.assignment && value.payload?.ai) result.push(value);
		} catch {
			/* A damaged local backup must not hide other drafts. */
		}
	}
	return result.sort((a, b) => b.updatedAt - a.updatedAt);
}

export function removeLocalDraft(owner: string, id: string) {
	localStorage.removeItem(key(owner, id));
}

export async function loadDraft(owner: string, id: string) {
	const backup = localDrafts(owner).find((item) => item.id === id);
	// A pending backup keeps its original revision: a later server edit must cause a conflict.
	if (backup) return { preparation: backup.preparation, backup };
	return {
		preparation: await teachingApi<Preparation>(`/teacher/teaching-preparations/${id}`),
		backup: undefined
	};
}

/** One request at a time, with synchronous local recovery before the debounce starts. */
export function createPreparationAutosave(options: {
	owner: string;
	assignmentId: string | null;
	initial: Preparation['payload'];
	preparation: Preparation | null;
	backup?: DraftBackup;
	onChange: (
		state: SaveState,
		preparation: Preparation | null,
		error?: unknown,
		localSafe?: boolean
	) => void;
	onId: (id: string) => void;
}) {
	let preparation = options.preparation;
	let id = options.backup?.id ?? preparation?.id ?? crypto.randomUUID();
	let latest = JSON.stringify(options.backup?.payload ?? options.initial);
	let saved = options.backup ? JSON.stringify(preparation?.payload ?? null) : latest;
	let timer: ReturnType<typeof setTimeout> | undefined;
	let flight: Promise<Preparation | null> | undefined;
	let stopped = false;
	let conflicted = false;
	let localSafe = true;
	let creationSnapshot = options.backup?.creationSnapshot;
	let uncertain = options.backup?.uncertain;
	const comparable = (payload: Preparation['payload']) => {
		// An omitted web_search has the same meaning as the API's explicit default.
		const ai = { ...payload.ai, web_search: payload.ai.web_search ?? false };
		return options.assignmentId ? ai : { ...payload, ai };
	};
	const matches = (a: Preparation['payload'], b: Preparation['payload']) =>
		fingerprint(comparable(a)) === fingerprint(comparable(b));
	const report = (state: SaveState, error?: unknown) => {
		if (!stopped) options.onChange(state, preparation, error, localSafe);
	};
	function backup() {
		try {
			localStorage.setItem(
				key(options.owner, id),
				JSON.stringify({
					id,
					assignmentId: options.assignmentId,
					preparation,
					payload: JSON.parse(latest),
					updatedAt: Date.now(),
					creationSnapshot,
					uncertain
				} satisfies DraftBackup)
			);
			localSafe = true;
		} catch {
			localSafe = false;
		}
	}
	async function write(): Promise<Preparation | null> {
		try {
			if (uncertain && preparation) {
				const remote = await teachingApi<Preparation>(`/teacher/teaching-preparations/${id}`);
				if (remote.revision !== uncertain.revision) {
					if (
						remote.revision !== uncertain.revision + 1 ||
						!matches(remote.payload, JSON.parse(uncertain.snapshot))
					)
						throw {
							status: 409,
							detail: 'Preparation changed; reload before saving. Your input has not been applied'
						};
					preparation = remote;
					saved = uncertain.snapshot;
				}
				uncertain = undefined;
			}
			while (!stopped && (latest !== saved || !preparation)) {
				const snapshot = latest;
				const payload = JSON.parse(snapshot);
				report('saving');
				let result: Preparation;
				if (!preparation) {
					creationSnapshot ??= snapshot;
					backup();
					result = await teachingApi<Preparation>('/teacher/teaching-preparations', 'POST', {
						id,
						assignment_id: options.assignmentId,
						payload: JSON.parse(creationSnapshot)
					});
					// Creation is idempotent even when its first response was lost.
					if (result.published)
						throw {
							status: 409,
							detail: 'This preparation has already been published; create a new preparation'
						};
					if (result.revision !== 1 || !matches(result.payload, JSON.parse(creationSnapshot)))
						throw {
							status: 409,
							detail: 'Preparation changed; reload before saving. Your input has not been applied'
						};
					preparation = result;
					if (creationSnapshot !== snapshot) {
						uncertain = { snapshot, revision: result.revision };
						backup();
						result = await teachingApi<Preparation>(`/teacher/teaching-preparations/${id}`, 'PUT', {
							expected_revision: result.revision,
							payload
						});
					}
				} else {
					uncertain = { snapshot, revision: preparation.revision };
					backup();
					result = await teachingApi<Preparation>(`/teacher/teaching-preparations/${id}`, 'PUT', {
						expected_revision: preparation.revision,
						payload
					});
				}
				preparation = result;
				uncertain = undefined;
				saved = snapshot;
				if (latest === snapshot) removeLocalDraft(options.owner, id);
				else backup();
			}
			if (latest === saved) removeLocalDraft(options.owner, id);
			report('saved');
			return preparation;
		} catch (error) {
			conflicted = (error as { status?: number })?.status === 409;
			backup();
			report(conflicted ? 'conflict' : 'failed', error);
			throw error;
		}
	}
	function flush() {
		clearTimeout(timer);
		if (conflicted)
			return Promise.reject(
				new Error('Preparation changed; reload before saving. Your input has not been applied')
			);
		if (flight) return flight;
		flight = write().finally(() => {
			flight = undefined;
		});
		return flight;
	}
	function observe(payload: Preparation['payload']) {
		const input = JSON.stringify(payload);
		if (input === latest) return;
		latest = input;
		backup();
		options.onId(id);
		clearTimeout(timer);
		if (!conflicted) {
			report('saving');
			timer = setTimeout(() => {
				void flush().catch(() => {});
			}, 600);
		}
	}
	if (options.backup) {
		options.onId(id);
		timer = setTimeout(() => {
			void flush().catch(() => {});
		}, 600);
	}
	return {
		observe,
		flush,
		get id() {
			return id;
		},
		get pending() {
			return latest !== saved;
		},
		get localSafe() {
			return localSafe;
		},
		async copyAfterConflict() {
			removeLocalDraft(options.owner, id);
			id = crypto.randomUUID();
			preparation = null;
			saved = '';
			conflicted = false;
			uncertain = undefined;
			creationSnapshot = undefined;
			backup();
			options.onId(id);
			return flush();
		},
		accept(result: Preparation) {
			preparation = result;
			latest = saved = JSON.stringify(result.payload);
			removeLocalDraft(options.owner, id);
			report('saved');
		},
		published() {
			stopped = true;
			clearTimeout(timer);
			removeLocalDraft(options.owner, id);
		},
		destroy() {
			stopped = true;
			clearTimeout(timer);
		}
	};
}

function fingerprint(value: unknown): string {
	return JSON.stringify(value, (_, item) =>
		item && typeof item === 'object' && !Array.isArray(item)
			? Object.fromEntries(
					Object.keys(item)
						.sort()
						.map((k) => [k, item[k]])
				)
			: item
	);
}
