// @vitest-environment jsdom
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { createPreparationAutosave, loadDraft, localDrafts } from './preparation-autosave';
import {
	assignmentFromPreparation,
	preparationAssignment,
	type Preparation
} from '$lib/apis/education/teaching';
import type { AssignmentDraft } from './assignment-form';
const api = vi.hoisted(() => vi.fn());
vi.mock('$lib/apis/education/teaching', async (original) => ({
	...(await original<typeof import('$lib/apis/education/teaching')>()),
	teachingApi: api
}));
const form: AssignmentDraft = {
	title: '',
	description: '',
	dueAt: '',
	scoreMax: '',
	scoringMode: 'dimensions',
	taskMode: 'from_scratch',
	coachingStyle: 'balanced',
	photoTranscriptionEnabled: false,
	imageReadingEnabled: true,
	challengeEnabled: true,
	challengeRounds: 2,
	challengeFocusKeys: ['one'],
	reflectionQuestions: [
		{
			id: 'q',
			kind: 'single_choice',
			prompt: '',
			options: [''],
			allow_other: false,
			required: true,
			show_when: 'always',
			placeholder: null
		}
	],
	rubricCriteria: [{ key: 'one', label: '', maxScore: '-' }],
	thinking: 'medium',
	studentsChooseThinking: true
};
const payload = () => ({
	assignment: preparationAssignment(form, []),
	ai: {
		prompt: '',
		model_id: '',
		template_version: 1,
		thinking: 'model_default' as const,
		web_search: false
	}
});
let remote: Preparation | null;
const controllers: ReturnType<typeof createPreparationAutosave>[] = [];
beforeEach(() => {
	vi.useFakeTimers();
	localStorage.clear();
	remote = null;
	api.mockReset();
	api.mockImplementation(async (_path, method, body) => {
		if (method === 'POST' && remote) return structuredClone(remote);
		if (method === 'POST' || method === 'PUT')
			remote = {
				id: body.id ?? remote!.id,
				revision: (remote?.revision ?? 0) + 1,
				assignment_id: null,
				base_config_revision: null,
				published: null,
				payload: structuredClone(body.payload)
			};
		return structuredClone(remote);
	});
});
afterEach(() => {
	controllers.splice(0).forEach((c) => c.destroy());
	vi.useRealTimers();
	localStorage.clear();
});
function controller(overrides = {}) {
	const result = createPreparationAutosave({
		owner: 't1',
		assignmentId: null,
		preparation: null,
		initial: payload(),
		onId: vi.fn(),
		onChange: vi.fn(),
		...overrides
	});
	controllers.push(result);
	return result;
}
const edit = (title: string) => {
	const p = payload();
	p.assignment.title = title;
	return p;
};

test('untouched form makes no request or local draft', async () => {
	const c = controller();
	c.observe(payload());
	await vi.advanceTimersByTimeAsync(1000);
	expect(api).not.toHaveBeenCalled();
	expect(localDrafts('t1')).toEqual([]);
});

test('all incomplete fields round trip without normalization or losing inactive settings', () => {
	expect(assignmentFromPreparation(preparationAssignment(form, []))).toEqual(form);
});

test('local recovery precedes debounce and is isolated by account', async () => {
	const c = controller();
	c.observe(edit('最新输入'));
	c.destroy();
	expect(api).not.toHaveBeenCalled();
	expect(localDrafts('t2')).toEqual([]);
	const restored = await loadDraft('t1', c.id);
	expect(restored.backup?.payload.assignment.title).toBe('最新输入');
	const next = controller({ backup: restored.backup, initial: restored.backup!.payload });
	await next.flush();
	expect(remote!.payload.assignment.title).toBe('最新输入');
	expect(localDrafts('t1')).toEqual([]);
});

test('edits during a slow save are serialized and flush waits for the latest input', async () => {
	const c = controller();
	const original = api.getMockImplementation()!;
	let release!: () => void;
	api.mockImplementationOnce(async (...args) => {
		await new Promise<void>((r) => {
			release = r;
		});
		return original(...args);
	});
	c.observe(edit('第一版'));
	const flushing = c.flush();
	c.observe(edit('第二版'));
	expect(api).toHaveBeenCalledTimes(1);
	expect(localDrafts('t1')[0].payload.assignment.title).toBe('第二版');
	release();
	await flushing;
	expect(remote!.payload.assignment.title).toBe('第二版');
	expect(api.mock.calls.filter(([, method]) => method === 'POST')).toHaveLength(1);
	expect(api.mock.calls[1][2].expected_revision).toBe(1);
	expect(c.pending).toBe(false);
});

test('lost create response reuses the same id instead of creating a second draft', async () => {
	const c = controller();
	const original = api.getMockImplementation()!;
	api.mockImplementationOnce(async (...args) => {
		await original(...args);
		throw new Error('network');
	});
	c.observe(edit('第一版'));
	await expect(c.flush()).rejects.toThrow('network');
	c.observe(edit('恢复后编辑'));
	await c.flush();
	expect(api.mock.calls[0][2].id).toBe(api.mock.calls[1][2].id);
	expect(remote!.payload.assignment.title).toBe('恢复后编辑');
});

test('copying an AI configuration with implicit web search disabled saves normally', async () => {
	const c = controller();
	const edited: Preparation['payload'] = edit('复制的段落论证作业');
	edited.assignment.task_mode = 'revise_argument';
	delete edited.ai.web_search;
	const original = api.getMockImplementation()!;
	api.mockImplementationOnce(async (path, method, body) =>
		original(path, method, {
			...body,
			payload: { ...body.payload, ai: { web_search: false, ...body.payload.ai } }
		})
	);
	c.observe(edited);
	await expect(c.flush()).resolves.toMatchObject({
		revision: 1,
		payload: { ai: { web_search: false } }
	});
	expect(c.pending).toBe(false);
});

test('lost update response is reconciled only when the saved content matches', async () => {
	const c = controller();
	c.observe(edit('第一版'));
	await c.flush();
	const original = api.getMockImplementation()!;
	api.mockImplementationOnce(async (...args) => {
		await original(...args);
		throw new Error('network');
	});
	c.observe(edit('第二版'));
	await expect(c.flush()).rejects.toThrow();
	await c.flush();
	expect(remote!.revision).toBe(2);
	expect(c.pending).toBe(false);
});

test('revision conflict retains input, does not retry over another tab, and allows a separate draft', async () => {
	const onChange = vi.fn();
	const c = controller({ onChange });
	c.observe(edit('本页内容'));
	await c.flush();
	api.mockRejectedValueOnce({ status: 409, detail: 'conflict' });
	c.observe(edit('冲突时本页内容'));
	await expect(c.flush()).rejects.toEqual({ status: 409, detail: 'conflict' });
	expect(onChange.mock.calls.at(-1)![0]).toBe('conflict');
	expect(localDrafts('t1')[0].payload.assignment.title).toBe('冲突时本页内容');
	const count = api.mock.calls.length;
	await vi.advanceTimersByTimeAsync(2000);
	expect(api).toHaveBeenCalledTimes(count);
	const oldId = c.id;
	remote = null;
	await c.copyAfterConflict();
	expect(c.id).not.toBe(oldId);
	expect(remote!.payload.assignment.title).toBe('冲突时本页内容');
});

test('a stale cached revision is preserved when reopening, not replaced by the server revision', async () => {
	const c = controller();
	c.observe(edit('原文'));
	await c.flush();
	api.mockRejectedValueOnce(new Error('offline'));
	c.observe(edit('离线修改'));
	await expect(c.flush()).rejects.toThrow();
	c.destroy();
	remote!.revision = 5;
	const loaded = await loadDraft('t1', c.id);
	expect(loaded.preparation!.revision).toBe(1);
	expect(loaded.backup!.payload.assignment.title).toBe('离线修改');
});

test('storage failure is reported while server saving can still succeed', async () => {
	const onChange = vi.fn();
	const c = controller({ onChange });
	const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
		throw new Error('quota');
	});
	c.observe(edit('待保存'));
	expect(c.localSafe).toBe(false);
	expect(onChange.mock.calls.at(-1)![3]).toBe(false);
	await c.flush();
	expect(remote!.payload.assignment.title).toBe('待保存');
	storage.mockRestore();
});

test('successful publication clears pending timers and local recovery', async () => {
	const c = controller();
	c.observe(edit('发布稿'));
	await c.flush();
	c.published();
	await vi.advanceTimersByTimeAsync(1000);
	expect(api).toHaveBeenCalledTimes(1);
	expect(localDrafts('t1')).toEqual([]);
});

test('lost create response never overwrites a later edit from another page', async () => {
	const c = controller();
	const original = api.getMockImplementation()!;
	api.mockImplementationOnce(async (...args) => {
		await original(...args);
		throw new Error('network');
	});
	c.observe(edit('本页'));
	await expect(c.flush()).rejects.toThrow();
	remote!.revision = 2;
	remote!.payload.assignment.title = '他页已保存';
	await expect(c.flush()).rejects.toMatchObject({ status: 409 });
	expect(remote!.payload.assignment.title).toBe('他页已保存');
	expect(api.mock.calls.some(([, method]) => method === 'PUT')).toBe(false);
});

test('existing assignment AI drafts accept the authoritative assignment preview', async () => {
	const c = controller({ assignmentId: 'published-a' });
	const original = api.getMockImplementation()!;
	api.mockImplementation(async (...args) => {
		const result = await original(...args);
		result.payload.assignment.title = '正式题目';
		return result;
	});
	c.observe(edit('未应用的题目编辑'));
	await c.flush();
	expect(c.pending).toBe(false);
});
