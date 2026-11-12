import { describe, expect, test } from 'vitest';

import { createSerializedSaveRunner } from './save-coordinator';

describe('createSerializedSaveRunner', () => {
	test('multiple simultaneous forced saves share one serial follow-up', async () => {
		let release!: () => void;
		let active = 0;
		let peak = 0;
		let count = 0;
		const save = createSerializedSaveRunner(async () => {
			active++;
			peak = Math.max(peak, active);
			count++;
			if (count === 1)
				await new Promise<void>((resolve) => {
					release = resolve;
				});
			active--;
		});
		const first = save('autosave');
		const second = save('manual', { force: true });
		const third = save('submit_preflight', { force: true });
		release();
		await Promise.all([first, second, third]);
		expect(peak).toBe(1);
		expect(count).toBe(2);
	});
	test('forced saves wait for an in-flight autosave and then run again', async () => {
		const calls: string[] = [];
		let releaseAutosave: () => void = () => {};
		let markAutosaveStarted: () => void = () => {};
		const autosaveStarted = new Promise<void>((resolve) => {
			markAutosaveStarted = resolve;
		});
		const submitFinished = new Promise<void>((resolve) => {
			const runner = createSerializedSaveRunner(async (reason) => {
				calls.push(reason);
				if (reason === 'autosave') {
					markAutosaveStarted();
					await new Promise<void>((release) => {
						releaseAutosave = release;
					});
					return;
				}

				resolve();
			});

			void runner('autosave');
			void autosaveStarted.then(() => runner('submit_preflight', { force: true }));
		});

		await autosaveStarted;
		expect(calls).toEqual(['autosave']);

		releaseAutosave();
		await submitFinished;

		expect(calls).toEqual(['autosave', 'submit_preflight']);
	});

	test('non-forced saves coalesce into one follow-up save after the current save', async () => {
		const calls: string[] = [];
		let releaseFirstSave: () => void = () => {};
		let markFirstSaveStarted: () => void = () => {};
		const firstSaveStarted = new Promise<void>((resolve) => {
			markFirstSaveStarted = resolve;
		});
		const secondSaveFinished = new Promise<void>((resolve) => {
			const runner = createSerializedSaveRunner(async (reason) => {
				calls.push(reason);
				if (calls.length === 1) {
					markFirstSaveStarted();
					await new Promise<void>((release) => {
						releaseFirstSave = release;
					});
					return;
				}

				resolve();
			});

			void runner('autosave');
			void firstSaveStarted.then(() => {
				void runner('autosave');
				void runner('autosave');
			});
		});

		await firstSaveStarted;
		expect(calls).toEqual(['autosave']);

		releaseFirstSave();
		await secondSaveFinished;

		expect(calls).toEqual(['autosave', 'autosave']);
	});
});
