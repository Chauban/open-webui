<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as I18n } from 'i18next';
	import { getContext, onMount, onDestroy } from 'svelte';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';
	import {
		submitDraftBaseline,
		getPendingWritingDraft,
		savePendingWritingDraft,
		downloadWritingWord
	} from '$lib/apis/education';
	import { resolveErrorMessage } from '$lib/utils/education';
	import type { ImportInfo } from '$lib/utils/text-import';
	import {
		textDocument,
		documentText,
		hasDocumentContent,
		type WritingNode
	} from '$lib/utils/writing-document';
	import { selectMaterial, type WritingMaterial } from '$lib/types/writing-materials';
	import EduButton from './EduButton.svelte';
	import TextImportActions from './TextImportActions.svelte';
	import WritingEditor from './WritingEditor.svelte';
	import WritingSaveNotice from './WritingSaveNotice.svelte';
	import { user } from '$lib/stores';
	import {
		createWritingBackup,
		downloadWritingBackup,
		type WritingBackup
	} from '$lib/utils/writing-backup';
	import { writingSaveProblem, type WritingSaveProblem } from '$lib/utils/writing-save';
	import UploadedOriginals from './UploadedOriginals.svelte';
	export let sessionId: string;
	export let photoTranscriptionEnabled = false;
	export let imageReadingEnabled = false;
	export let onSubmitted: () => Promise<void> | void;
	const i18n = getContext<Writable<I18n>>('i18n');
	const t = (key: string) => get(i18n).t(key);
	const MIN_CHARS = 200;
	let document: WritingNode = textDocument('');
	let materials: WritingMaterial[] = [];
	let revision = 0;
	let saved = '';
	let loading = true;
	let loadFailed = false;
	let importing = false;
	let submitting = false;
	let downloading = false;
	let dragging = false;
	let error = '';
	let problem: WritingSaveProblem | null = null;
	let localSafe = true;
	let backups: WritingBackup[] = [];
	let backupStore: ReturnType<typeof createWritingBackup<any>> | null = null;
	let recovered: WritingBackup | null = null;
	let retryAttempt = 0;
	function backup() {
		try {
			backupStore?.write({ document, materials, revision });
			localSafe = !!backupStore;
		} catch {
			localSafe = false;
		}
	}
	function discard(item: WritingBackup) {
		try {
			backupStore?.discard(item);
			backups = backups.filter((b) => b.id !== item.id);
		} catch {
			localSafe = false;
		}
	}
	function restore(item: WritingBackup) {
		if (busy) return;
		if (item.data.revision !== revision) {
			error = t('服务器初稿已变化，请下载备份后核对，不能直接覆盖当前初稿。');
			return;
		}
		document = structuredClone(item.data.document);
		materials = structuredClone(item.data.materials);
		recovered = item;
		backups = backups.filter((b) => b.id !== item.id);
		changed();
	}
	function failed(err: unknown) {
		problem = writingSaveProblem(err);
		error = '';
		backup();
		if (!disposed && problem.retryable && retryAttempt < 3) {
			if (timer) clearTimeout(timer);
			const delay = Math.max([2000, 4000, 8000][retryAttempt++], problem.retryAfterMs || 0);
			timer = setTimeout(() => {
				timer = null;
				void save().catch(failed);
			}, delay);
		}
	}
	async function copy() {
		try {
			await navigator.clipboard.writeText(text);
			toast.success(t('全文已复制。'));
		} catch {
			toast.error(t('复制失败，请下载文字备份。'));
		}
	}
	let importer: TextImportActions;
	let editor: any = null;
	let timer: ReturnType<typeof setTimeout> | null = null;
	let queue = Promise.resolve();
	let disposed = false;
	$: text = documentText(document);
	$: charCount = text.replace(/\s/g, '').length;
	$: busy = loading || loadFailed || importing || submitting;
	const fingerprint = () => JSON.stringify({ document, materials: materials.map((m) => m.id) });
	onMount(async () => {
		backupStore = createWritingBackup($user?.id ?? '', sessionId, 'baseline');
		try {
			backups = backupStore.list();
		} catch {
			localSafe = false;
		}
		try {
			const state = await getPendingWritingDraft(localStorage.token, sessionId);
			if (disposed) return;
			document = state.content_json;
			materials = state.materials;
			revision = state.revision;
			saved = fingerprint();
		} catch (err) {
			error = resolveErrorMessage(err, t);
			loadFailed = true;
		} finally {
			loading = false;
		}
	});
	onDestroy(() => {
		disposed = true;
		if (timer) {
			clearTimeout(timer);
			backup();
		}
	});
	function save() {
		if (timer) {
			clearTimeout(timer);
			timer = null;
		}
		const next = queue
			.catch(() => {})
			.then(async () => {
				const mark = fingerprint();
				if (disposed || mark === saved || loading || loadFailed) return;
				const content = structuredClone(document);
				const selected = materials.map(selectMaterial);
				const result = await savePendingWritingDraft(localStorage.token, sessionId, {
					content_json: content,
					materials: selected,
					expected_revision: revision
				});
				revision = result.revision;
				saved = mark;
				error = '';
				problem = null;
				retryAttempt = 0;
				if (mark === fingerprint()) {
					try {
						backupStore?.clear();
						if (recovered) backupStore?.discard(recovered);
						recovered = null;
					} catch {
						localSafe = false;
					}
				} else backup();
			});
		queue = next;
		return next;
	}
	function changed() {
		retryAttempt = 0;
		backup();
		if (timer) clearTimeout(timer);
		timer = setTimeout(() => {
			timer = null;
			void save().catch(failed);
		}, 800);
	}
	function onImported(imported: string, info: ImportInfo) {
		const incoming = info.document ?? textDocument(imported);
		const originals = info.materials ?? (info.material ? [info.material] : []);
		if (hasDocumentContent(document)) {
			if (editor) editor.chain().focus().insertContent(incoming.content).run();
			else
				document = {
					type: 'doc',
					content: [...(document.content ?? []), ...(incoming.content ?? [])]
				};
			materials = [...materials, ...originals];
		} else {
			document = incoming;
			materials = originals;
		}
		if (info.purpose === 'photo_to_text')
			toast.success(t('照片文字已进入编辑框，请对照原稿核对；□ 表示未辨认清楚的字。'));
		changed();
	}
	async function confirm() {
		if (busy || backups.length || charCount < MIN_CHARS) return;
		submitting = true;
		try {
			await save();
			await submitDraftBaseline(
				localStorage.token,
				sessionId,
				text,
				materials.map(selectMaterial),
				document,
				revision
			);
			try {
				backupStore?.clear();
			} catch {
				localSafe = false;
			}
			await onSubmitted();
		} catch (err) {
			failed(err);
		} finally {
			submitting = false;
		}
	}
	async function download() {
		downloading = true;
		try {
			await save();
			await downloadWritingWord(localStorage.token, {
				sessionId,
				pending: true,
				contentJson: document
			});
		} catch (err) {
			toast.error(resolveErrorMessage(err, t));
		} finally {
			downloading = false;
		}
	}
</script>

<section class="flex min-h-0 flex-1 flex-col">
	<div class="flex min-h-0 flex-1 flex-col overflow-y-auto pb-4">
		<div class="shrink-0">
			<h3 class="text-sm font-semibold">{$i18n.t('Submit your first draft')}</h3>
			<p class="mt-1 mb-3 text-sm text-gray-500">
				{$i18n.t('Paste or upload your draft. Confirm it to start revising and chatting with AI.')}
			</p>
			<div class="flex flex-wrap items-center justify-between gap-2">
				<TextImportActions
					baselineHelp
					{photoTranscriptionEnabled}
					{imageReadingEnabled}
					bind:this={importer}
					bind:busy={importing}
					{sessionId}
					disabled={submitting || loading || loadFailed}
					{onImported}
				/>
				<EduButton
					size="sm"
					disabled={busy || downloading || !hasDocumentContent(document)}
					on:click={download}>{$i18n.t('下载当前稿（Word）')}</EduButton
				>
			</div>
			<WritingSaveNotice
				{problem}
				{localSafe}
				{backups}
				{busy}
				readonly={loadFailed}
				onRetry={() => void save().catch(failed)}
				onCopy={copy}
				onLogin={() => {
					backup();
					window.location.assign(`/auth?redirect=${encodeURIComponent(window.location.pathname)}`);
				}}
				onDownload={() => downloadWritingBackup(document)}
				onRestore={restore}
				onDiscard={discard}
				onDownloadBackup={(item) => downloadWritingBackup(item.data.document)}
			/>
			<UploadedOriginals {materials} />
			{#if !imageReadingEnabled && materials.length}<p class="my-2 text-xs text-gray-500">
					{$i18n.t('AI 本次只读取文字，图片仍会随作业保存。')}
				</p>{/if}
		</div>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="draft-editor mt-3 flex flex-1 shrink-0 flex-col rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900 {dragging
				? 'ring-2 ring-sky-400'
				: ''}"
			on:dragover|preventDefault={() => (dragging = true)}
			on:dragleave={() => (dragging = false)}
			on:drop={(event) => {
				dragging = false;
				if (!event.defaultPrevented && event.dataTransfer?.files.length) {
					event.preventDefault();
					void importer.importFiles(Array.from(event.dataTransfer.files));
				}
			}}
		>
			<WritingEditor
				bind:editor
				onImportFiles={async (files) => {
					dragging = false;
					await importer.importFiles(files);
				}}
				bind:value={document}
				{sessionId}
				{imageReadingEnabled}
				editable={!busy}
				className="input-prose"
				placeholder={$i18n.t('Paste your first draft here, or drop a file in')}
				onChange={(content) => {
					if (content.docChanged && !content.programmatic && !busy) {
						document = content.json;
						changed();
					}
				}}
			/>
		</div>
		{#if charCount < MIN_CHARS && hasDocumentContent(document)}<p
				class="mt-2 shrink-0 text-xs text-gray-500"
			>
				{$i18n.t('请补充至少 200 字正文。图片和未转入正文的识别文字不计入字数。')}
			</p>{/if}
		{#if error}<p role="alert" class="mt-2 shrink-0 text-sm text-red-600">{error}</p>{/if}
	</div>
	<div
		class="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-gray-200 bg-stone-50 pt-3 pb-[env(safe-area-inset-bottom)] dark:border-gray-700 dark:bg-gray-900"
	>
		<div
			class="text-xs tabular-nums {charCount < MIN_CHARS ? 'text-gray-500' : 'text-emerald-600'}"
		>
			{$i18n.t('{{count}} / {{min}} characters at least', { count: charCount, min: MIN_CHARS })}
		</div>
		<EduButton
			variant="primary"
			disabled={busy || backups.length > 0 || charCount < MIN_CHARS}
			on:click={confirm}
			>{submitting ? $i18n.t('Saving...') : $i18n.t('Confirm this is my first draft')}</EduButton
		>
	</div>
</section>

<style>
	.draft-editor :global(.writing-editor),
	.draft-editor :global(.input-prose) {
		display: flex;
		flex: 1 0 auto;
		flex-direction: column;
	}

	/* Put spacing on the editable surface so its blank area also accepts the caret.
	   Override the shared ProseMirror height rules only for the initial draft. */
	.draft-editor :global(.tiptap) {
		flex: 1 0 auto;
		height: auto;
		min-height: 16rem;
		max-height: none;
		padding: 1rem 1.25rem;
	}
</style>
