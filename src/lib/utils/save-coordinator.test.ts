import { describe, expect, test } from 'vitest';

import { createSerializedSaveRunner } from './save-coordinator';

describe('createSerializedSaveRunner', () => {
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
