import { documentText, type WritingNode } from './writing-document';

export type WritingBackup<T = any> = {
	id: string;
	updatedAt: number;
	data: T & { document: WritingNode };
};

/** Each open workspace owns a separate record. A late save cannot erase another tab's draft. */
export function createWritingBackup<T extends { document: WritingNode }>(
	owner: string,
	session: string,
	stage: 'draft' | 'baseline'
) {
	const prefix = `writing-backup:${encodeURIComponent(owner)}:${encodeURIComponent(session)}:${stage}:`;
	const id = crypto.randomUUID();
	const key = prefix + id;
	let lastWritten = '';
	return {
		list(): WritingBackup<T>[] {
			const records: WritingBackup<T>[] = [];
			for (let i = 0; i < localStorage.length; i++) {
				const name = localStorage.key(i)!;
				if (!name.startsWith(prefix) || name === key) continue;
				const record = JSON.parse(localStorage.getItem(name)!);
				if (
					record?.id === name.slice(prefix.length) &&
					Number.isFinite(record.updatedAt) &&
					record.data?.document?.type === 'doc'
				)
					records.push(record);
			}
			return records.sort((a, b) => b.updatedAt - a.updatedAt);
		},
		write(data: T) {
			if (!owner || !session) throw new Error('A signed-in writing session is required');
			lastWritten = JSON.stringify({ id, updatedAt: Date.now(), data });
			localStorage.setItem(key, lastWritten);
		},
		clear() {
			// The caller only acknowledges the snapshot that actually completed all save steps.
			if (localStorage.getItem(key) === lastWritten) localStorage.removeItem(key);
		},
		discard(record: WritingBackup<T>) {
			if (localStorage.getItem(prefix + record.id) === JSON.stringify(record))
				localStorage.removeItem(prefix + record.id);
		}
	};
}

export function downloadWritingBackup(document: WritingNode) {
	const url = URL.createObjectURL(
		new Blob([documentText(document)], { type: 'text/plain;charset=utf-8' })
	);
	const link = window.document.createElement('a');
	link.href = url;
	link.download = '稿件备份.txt';
	link.click();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
}
