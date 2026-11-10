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
	import UploadedOriginals from './UploadedOriginals.svelte';
	export let sessionId: string;
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
	let importer: TextImportActions;
	let editor: any = null;
	let insertAtCursor = false;
	let timer: ReturnType<typeof setTimeout> | null = null;
	let queue = Promise.resolve();
	let disposed = false;
	$: text = documentText(document);
	$: charCount = text.replace(/\s/g, '').length;
	$: busy = loading || loadFailed || importing || submitting;
	const fingerprint = () => JSON.stringify({ document, materials: materials.map((m) => m.id) });
	onMount(async () => {
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
			void save().catch(() => {});
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
				if (mark === saved || loading || loadFailed) return;
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
			});
		queue = next;
		return next;
	}
	function changed() {
		if (timer) clearTimeout(timer);
		timer = setTimeout(() => {
			timer = null;
			void save().catch((err) => {
				error = resolveErrorMessage(err, t);
			});
		}, 800);
	}
	function onImported(imported: string, info: ImportInfo) {
		const incoming = info.document ?? textDocument(imported);
		const originals = info.materials ?? (info.material ? [info.material] : []);
		if (insertAtCursor && editor) {
			editor.chain().focus().insertContent(incoming.content).run();
			materials = [...materials, ...originals];
		} else {
			document = incoming;
			materials = originals;
		}
		changed();
	}
	async function confirm() {
		if (busy || charCount < MIN_CHARS) return;
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
			await onSubmitted();
		} catch (err) {
			error = resolveErrorMessage(err, t);
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
	<div class="min-h-0 flex-1 overflow-y-auto pb-4">
		<h3 class="text-sm font-semibold">{$i18n.t('Submit your first draft')}</h3>
		<p class="mt-1 mb-3 text-sm text-gray-500">
			{$i18n.t('Paste or upload your draft. Confirm it to start revising and chatting with AI.')}
		</p>
		<div class="flex flex-wrap items-center justify-between gap-2">
			<TextImportActions
				baselineHelp
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
		<UploadedOriginals {materials} />
		{#if !imageReadingEnabled && materials.length}<p class="my-2 text-xs text-gray-500">
				{$i18n.t('AI 本次只读取文字，图片仍会随作业保存。')}
			</p>{/if}
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="mt-3 rounded-xl border border-gray-200 bg-white px-5 py-4 dark:border-gray-700 dark:bg-gray-900 {dragging
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
				onImportFiles={async (files, source) => {
					dragging = false;
					insertAtCursor = source === 'paste';
					try {
						await importer.importFiles(files);
					} finally {
						insertAtCursor = false;
					}
				}}
				bind:value={document}
				{sessionId}
				{imageReadingEnabled}
				editable={!busy}
				className="input-prose min-h-64 [&>.tiptap]:min-h-64"
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
				class="mt-2 text-xs text-gray-500"
			>
				{$i18n.t('请补充至少 200 字正文。图片和未转入正文的识别文字不计入字数。')}
			</p>{/if}
		{#if error}<p role="alert" class="mt-2 text-sm text-red-600">{error}</p>{/if}
	</div>
	<div
		class="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-gray-200 bg-stone-50 pt-3 pb-[env(safe-area-inset-bottom)] dark:border-gray-700 dark:bg-gray-900"
	>
		<div
			class="text-xs tabular-nums {charCount < MIN_CHARS ? 'text-gray-500' : 'text-emerald-600'}"
		>
			{$i18n.t('{{count}} / {{min}} characters at least', { count: charCount, min: MIN_CHARS })}
		</div>
		<EduButton variant="primary" disabled={busy || charCount < MIN_CHARS} on:click={confirm}
			>{submitting ? $i18n.t('Saving...') : $i18n.t('Confirm this is my first draft')}</EduButton
		>
	</div>
</section>
