<script lang="ts">
	// @ts-nocheck
	import { getContext, onDestroy, onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import { mobile, selectedFolder } from '$lib/stores';

	import RichTextInput from '$lib/components/common/RichTextInput.svelte';
	import Chat from '$lib/components/chat/Chat.svelte';
	import { prepareAssistantContentForWriting } from '$lib/utils/writing-content';
	import { createSerializedSaveRunner } from '$lib/utils/save-coordinator';
	import {
		applySourceMapChange,
		normalizeSourceRuns,
		provenanceSegmentsToSourceRuns,
		sourceRunsToProvenanceSegments
	} from '$lib/utils/writing-source-map';
	import {
		autosaveWritingSession,
		createEditorOperations,
		createProvenanceSegments,
		createWritingVersion,
		setWritingSessionActiveChat,
		submitAssignment
	} from '$lib/apis/education';
	import { updateFolderById } from '$lib/apis/folders';
	import { updateNoteById } from '$lib/apis/notes';

	export let scope: 'assignment' | 'personal' = 'assignment';
	export let projectBaseUrl = '/me/writing';
	export let loadWorkspace: () => Promise<any>;

	const i18n = getContext('i18n');

	let loaded = false;
	let loadError = '';
	let assignment = null;
	let writingSession = null;
	let workspaceProject = null;
	let workspaceNote = null;
	let currentChatId = '';
	let editor = null;
	let noteJson = null;
	let noteText = '';
	let noteHtml = '';
	let noteTitle = '';
	let saveStatusKey = 'Unsaved';
	let saving = false;
	let showSubmitModal = false;
	let showMobileDraft = false;
	let isSubmitted = false;
	let titleSaving = false;
	let isPastDue = false;
	let isReadOnly = false;
	let canSubmitAssignment = false;

	let aiHelpTypes = ["Help Break Through Writer's Block"];
	let otherAiHelpText = '';
	let reflectionText = '';

	let lastText = '';
	let pendingSource: null | { sourceType: string; sourceMessageId?: string | null; text?: string } =
		null;
	let sourceRuns = [];
	let unsavedOperations = [];
	let autoSaveTimer: ReturnType<typeof setTimeout> | null = null;
	let lastPersistedActiveChatId: string | null | undefined = undefined;

	const helpTypes = [
		'Understand Assignment',
		'Outline',
		'Examples',
		'Explain Concepts',
		'Revise Structure',
		'Polish',
		'Check Errors',
		"Help Break Through Writer's Block",
		'Strengthen Reasoning',
		'Other'
	];

	const isAssignment = scope === 'assignment';
	$: isPastDue =
		isAssignment && assignment?.due_at ? assignment.due_at <= Math.floor(Date.now() / 1000) : false;
	$: isReadOnly = isAssignment ? isPastDue : false;
	$: canSubmitAssignment = isAssignment && !isPastDue;
	const getDefaultPersonalTitle = () => get(i18n).t('Untitled Writing');
	const normalizePersonalTitle = (value?: string | null) => {
		const normalized = value?.trim();
		if (!normalized || normalized === 'Untitled Writing') {
			return getDefaultPersonalTitle();
		}
		return normalized;
	};

	$: if (!aiHelpTypes.includes('Other') && otherAiHelpText) {
		otherAiHelpText = '';
	}

	const getSubmitReflectionText = () => {
		const baseReflection = reflectionText.trim();
		if (!aiHelpTypes.includes('Other')) {
			return baseReflection;
		}

		const otherDetail = otherAiHelpText.trim();
		return `其他帮助内容：${otherDetail}\n\n${baseReflection}`.trim();
	};

	const toggleAiHelpType = (helpType: string) => {
		aiHelpTypes = aiHelpTypes.includes(helpType)
			? aiHelpTypes.filter((item) => item !== helpType)
			: [...aiHelpTypes, helpType];
	};

	const makeSegment = (
		sourceType: string,
		segmentText: string,
		sourceMessageId?: string | null
	) => ({
		segment_id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`,
		source_type: sourceType,
		segment_text: segmentText,
		source_message_id: sourceMessageId ?? null,
		start_offset: null,
		end_offset: null,
		metadata_json: null
	});

	const makeBatchId = () =>
		crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;

	const queueOperation = (operation) => {
		unsavedOperations = [...unsavedOperations, operation];
	};

	const updateTrackedOperation = (batchId: string, payload: Record<string, unknown>) => {
		unsavedOperations = unsavedOperations.map((operation) =>
			operation.batch_id === batchId ? { ...operation, ...payload } : operation
		);
	};

	const extractInsertedSegment = (prev: string, next: string) => {
		if (next.length <= prev.length) return null;

		let start = 0;
		while (start < prev.length && prev[start] === next[start]) {
			start += 1;
		}

		let end = 0;
		while (
			end < prev.length - start &&
			prev[prev.length - 1 - end] === next[next.length - 1 - end]
		) {
			end += 1;
		}

		const inserted = next.slice(start, next.length - end);
		if (!inserted.trim()) return null;

		return { inserted, startOffset: start, endOffset: start + inserted.length };
	};

	const extractTextDiff = (prev: string, next: string) => {
		if (prev === next) return null;

		let start = 0;
		while (start < prev.length && start < next.length && prev[start] === next[start]) {
			start += 1;
		}

		let prevEnd = prev.length - 1;
		let nextEnd = next.length - 1;
		while (prevEnd >= start && nextEnd >= start && prev[prevEnd] === next[nextEnd]) {
			prevEnd -= 1;
			nextEnd -= 1;
		}

		return {
			startOffset: start,
			endOffset: start + Math.max(nextEnd - start + 1, 0),
			insertedText: next.slice(start, nextEnd + 1),
			deletedText: prev.slice(start, prevEnd + 1)
		};
	};

	const scheduleSave = () => {
		saveStatusKey = 'Saving...';
		if (autoSaveTimer) clearTimeout(autoSaveTimer);
		autoSaveTimer = setTimeout(() => {
			void persistDraft('autosave');
		}, 1200);
	};

	const performPersistDraft = async (triggerType = 'autosave') => {
		if (!writingSession || isReadOnly) return;
		saving = true;
		saveStatusKey = 'Saving...';

		try {
			await autosaveWritingSession(localStorage.token, writingSession.id, {
				content_json: noteJson,
				content_html: noteHtml,
				content_text: noteText,
				save_reason: triggerType
			});

			const version = await createWritingVersion(localStorage.token, writingSession.id, {
				trigger_type: triggerType,
				content_json: noteJson,
				content_text: noteText
			});

			if (unsavedOperations.length > 0) {
				await createEditorOperations(localStorage.token, writingSession.id, {
					operations: unsavedOperations
				});
				unsavedOperations = [];
			}

			await createProvenanceSegments(localStorage.token, writingSession.id, {
				version_id: version.id,
				replace_existing: true,
				segments: sourceRunsToProvenanceSegments(noteText, sourceRuns)
			});

			saveStatusKey = isSubmitted ? 'Submitted' : 'Saved';
		} catch (error) {
			console.error(error);
			saveStatusKey = 'Save failed';
		} finally {
			saving = false;
		}
	};

	const runPersistDraft = createSerializedSaveRunner(performPersistDraft);

	const persistDraft = async (triggerType = 'autosave', options = {}) => {
		return runPersistDraft(triggerType, options);
	};

	const saveTitle = async () => {
		if (isAssignment || !workspaceNote?.id || titleSaving) return;
		const nextTitle = noteTitle.trim() || getDefaultPersonalTitle();
		if (nextTitle === workspaceNote?.title) {
			noteTitle = nextTitle;
			return;
		}

		titleSaving = true;
		try {
			workspaceNote = await updateNoteById(localStorage.token, workspaceNote.id, {
				...workspaceNote,
				title: nextTitle
			});
			noteTitle = normalizePersonalTitle(workspaceNote.title);
			if (workspaceProject) {
				workspaceProject = await updateFolderById(localStorage.token, workspaceProject.id, {
					...workspaceProject,
					name: nextTitle
				});
				selectedFolder.set(workspaceProject);
			}
		} catch (error) {
			toast.error(`${error}`);
		} finally {
			titleSaving = false;
		}
	};

	const handleContentChange = (content) => {
		if (isReadOnly) return;
		noteJson = content.json;
		noteHtml = content.html;
		noteText = content.text ?? content.md;
		const diff = extractTextDiff(lastText, noteText);
		const sourceType = pendingSource?.sourceType ?? 'user_typed';
		const sourceMessageId = pendingSource?.sourceMessageId ?? null;

		sourceRuns = applySourceMapChange({
			previousText: lastText,
			nextText: noteText,
			runs: sourceRuns,
			source: { sourceType, sourceMessageId }
		});

		if (diff) {
			let opType = 'keyboard_input';
			if (diff.insertedText && diff.deletedText) opType = 'replace';
			else if (diff.deletedText) opType = 'delete_text';
			else if (sourceType === 'ai_inserted') opType = 'ai_insert_clicked';
			else if (sourceType === 'ai_pasted' || sourceType === 'external_paste' || sourceType === 'paste') {
				opType = 'paste_detected';
			}

			queueOperation({
				op_type: opType,
				source_type: sourceType,
				start_offset: diff.startOffset,
				end_offset: diff.endOffset,
				inserted_text: diff.insertedText || null,
				deleted_text: diff.deletedText || null,
				batch_id: makeBatchId(),
				metadata_json: null
			});
		}

		lastText = noteText;
		pendingSource = null;
		scheduleSave();
	};

	const insertAssistantContent = async (message) => {
		if (isReadOnly || !editor) return;
		const preparedContent = prepareAssistantContentForWriting({
			content: `${message.content ?? ''}`
		});
		const insertedText = preparedContent.text;
		if (!insertedText) return;
		pendingSource = {
			sourceType: 'ai_inserted',
			sourceMessageId: message.id ?? null,
			text: insertedText
		};
		editor.chain().focus().insertContent(preparedContent.html).run();
	};

	const copyAssistantContentWithSource = async (message) => {
		const preparedContent = prepareAssistantContentForWriting({
			content: `${message.content ?? ''}`
		});
		if (message.selectionCopy) {
			queueOperation({
				op_type: 'ai_reply_selection_copied',
				source_type: 'ai_pasted',
				start_offset: null,
				end_offset: null,
				inserted_text: null,
				deleted_text: null,
				batch_id: makeBatchId(),
				metadata_json: {
					source_message_id: message.id ?? null,
					copy_length: preparedContent.text.length
				}
			});
			scheduleSave();
			return;
		}

		await navigator.clipboard.write([
			new ClipboardItem({
				'text/html': new Blob([preparedContent.html], { type: 'text/html' }),
				'text/plain': new Blob([preparedContent.text], { type: 'text/plain' }),
				'application/x-openwebui-ai-snippet+json': new Blob(
					[
						JSON.stringify({
							sourceType: 'ai_pasted',
							sourceMessageId: message.id ?? null,
							text: preparedContent.text
						})
					],
					{ type: 'application/x-openwebui-ai-snippet+json' }
				)
			})
		]);
		queueOperation({
			op_type: 'ai_copy_button_clicked',
			source_type: 'ai_pasted',
			start_offset: null,
			end_offset: null,
			inserted_text: null,
			deleted_text: null,
			batch_id: makeBatchId(),
			metadata_json: {
				source_message_id: message.id ?? null,
				copy_length: preparedContent.text.length
			}
		});
		scheduleSave();
		toast.success($i18n.t('Copied with source'));
	};

	const submit = async () => {
		if (!canSubmitAssignment) return;
		if (aiHelpTypes.length === 0) {
			toast.error($i18n.t('Select at least one AI help type.'));
			return;
		}
		if (aiHelpTypes.includes('Other') && otherAiHelpText.trim().length === 0) {
			toast.error('请简单写一下 AI 还帮助了你什么。');
			return;
		}

		const submitReflectionText = getSubmitReflectionText();
		if (submitReflectionText.length < 30) {
			toast.error($i18n.t('Reflection must be at least 30 characters.'));
			return;
		}

		await persistDraft('submit_preflight', { force: true });

		try {
			await submitAssignment(localStorage.token, assignment.id, {
				writing_session_id: writingSession.id,
				final_content_json: noteJson,
				final_content_html: noteHtml,
				final_content_text: noteText,
				ai_help_types: aiHelpTypes,
				reflection_text: submitReflectionText
			});
			toast.success($i18n.t('Assignment submitted'));
			await goto('/me/writing');
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		}
	};

	const load = async () => {
		try {
			const workspace = await loadWorkspace();
			assignment = workspace.assignment ?? null;
			writingSession = workspace.writing_session;
			workspaceProject = workspace.project;
			workspaceNote = workspace.note;
			isSubmitted = workspace.writing_session?.status === 'submitted';
			saveStatusKey = isSubmitted ? 'Submitted' : 'Saved';
			noteJson = workspace.note?.data?.content?.json ?? null;
			noteHtml = workspace.note?.data?.content?.html ?? '';
			noteText = workspace.note?.data?.content?.md ?? '';
			noteTitle = normalizePersonalTitle(workspace.note?.title);
			lastText = noteText;
			sourceRuns = workspace.source_map?.length
				? provenanceSegmentsToSourceRuns(noteText, workspace.source_map)
				: normalizeSourceRuns([], noteText.length);
			currentChatId = $page.url.searchParams.get('chat') ?? '';
			await selectedFolder.set(workspaceProject);
			loaded = true;
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		}
	};

	onMount(load);

	onDestroy(() => {
		if (
			$selectedFolder?.meta?.mode === 'assignment_writing' ||
			$selectedFolder?.meta?.mode === 'personal_writing' ||
			$selectedFolder?.meta?.category === 'assignment_project' ||
			$selectedFolder?.meta?.category === 'personal_writing'
		) {
			selectedFolder.set(null);
		}
	});

	$: if (loaded && workspaceProject?.id && $selectedFolder?.id !== workspaceProject.id) {
		selectedFolder.set(workspaceProject);
	}

	$: if (loaded) {
		currentChatId = $page.url.searchParams.get('chat') ?? '';
	}

	$: if (loaded && writingSession?.id && currentChatId && lastPersistedActiveChatId !== currentChatId) {
		lastPersistedActiveChatId = currentChatId;
		void setWritingSessionActiveChat(localStorage.token, writingSession.id, currentChatId || null).catch(
			(error) => {
				console.error(error);
			}
		);
	}
</script>

{#if loaded}
	<Chat
		chatIdProp={currentChatId}
		projectBaseUrl={projectBaseUrl}
		responseInsertHandler={isReadOnly ? null : insertAssistantContent}
		responseCopyHandler={copyAssistantContentWithSource}
		responseInsertLabel={'Insert to Writing'}
		readOnly={isReadOnly}
		disableContextActions={false}
		allowAssignmentWorkspaceChat={isAssignment}
		showModelSelector={true}
		showRightPanel={!$mobile}
		rightPanelDefaultSize={34}
		rightPanelMinSize={26}
		rightPanelClassName="hidden lg:flex"
	>
		<div
			slot="right-panel"
			class="h-full w-full flex-col border-l border-gray-200 bg-stone-50 lg:flex"
		>
			<div class="border-b border-gray-200 bg-white px-5 py-4">
				<div class="flex items-start justify-between gap-4">
					<div class="min-w-0 flex-1">
						<div class="text-xs uppercase tracking-[0.18em] text-gray-500">
							{$i18n.t(isAssignment ? 'Assignment Writing' : '写作')}
						</div>
						{#if isAssignment}
							<div class="text-sm font-semibold text-gray-900">{assignment?.title}</div>
							<div class="text-xs text-gray-500">
								{#if isPastDue}
									{$i18n.t('Submitted assignments stay available for review in read-only mode.')}
								{:else if isSubmitted}
									{$i18n.t('Submitted. You can revise and resubmit before the deadline.')}
								{:else}
									{$i18n.t('Track typed text, AI insertions, and in-app AI paste.')}
								{/if}
							</div>
						{:else}
							<input
								bind:value={noteTitle}
								class="mt-1 w-full rounded-2xl border border-gray-200 px-3 py-2 text-sm font-semibold text-gray-900 outline-none"
								placeholder={$i18n.t('Untitled Writing')}
								on:blur={saveTitle}
							/>
							<div class="mt-1 text-xs text-gray-500">{$i18n.t('Write freely. Autosaved.')}</div>
						{/if}
					</div>
					<div class="flex items-center gap-2">
						{#if isSubmitted}
							<div class="rounded-full bg-emerald-100 px-3 py-1 text-xs text-emerald-700">
								{$i18n.t('Submitted')}
							</div>
						{/if}
						<div class="rounded-full bg-stone-100 px-3 py-1 text-xs text-gray-600">
							{$i18n.t(saveStatusKey)}
						</div>
						{#if canSubmitAssignment}
							<button
								class="rounded-full bg-gray-900 px-4 py-2 text-sm text-white"
								on:click={() => {
									showSubmitModal = true;
								}}
							>
								{$i18n.t('Submit Assignment')}
							</button>
						{/if}
					</div>
				</div>
			</div>
			<div class="min-h-0 flex-1 overflow-y-auto px-5 py-5">
				<RichTextInput
					bind:editor
					bind:value={noteJson}
					editable={!isReadOnly}
					json={true}
					placeholder={$i18n.t(isAssignment ? 'Write the final assignment here.' : 'Start writing...')}
					className="input-prose min-h-[70vh]"
					onChange={handleContentChange}
					on:paste={async (event) => {
						const clipboardEvent = event?.detail?.event ?? event;
						const payload =
							clipboardEvent?.clipboardData?.getData('application/x-openwebui-ai-snippet+json') ??
							'';
						if (!payload) {
							pendingSource = {
								sourceType: 'external_paste',
								sourceMessageId: null,
								text: ''
							};
							return;
						}
						try {
							const meta = JSON.parse(payload);
							pendingSource = {
								sourceType: meta.sourceType ?? 'ai_pasted',
								sourceMessageId: meta.sourceMessageId ?? null,
								text: meta.text ?? ''
							};
						} catch (error) {
							console.error(error);
						}
					}}
				/>
			</div>
		</div>
	</Chat>

	{#if $mobile}
		<div class="pointer-events-none fixed inset-x-0 bottom-4 z-30 flex justify-center px-4">
			<div
				class="pointer-events-auto flex items-center gap-2 rounded-full border border-gray-200 bg-white/95 px-3 py-2 shadow-lg backdrop-blur"
			>
				<div class="rounded-full bg-stone-100 px-3 py-1 text-xs text-gray-600">
					{$i18n.t(saveStatusKey)}
				</div>
				<button
					class="rounded-full border border-gray-300 px-3 py-1.5 text-sm text-gray-700"
					on:click={() => {
						showMobileDraft = true;
					}}
				>
					{$i18n.t(isAssignment ? 'Assignment Content' : 'Writing Content')}
				</button>
				{#if canSubmitAssignment}
					<button
						class="rounded-full bg-gray-900 px-3 py-1.5 text-sm text-white"
						on:click={() => {
							showSubmitModal = true;
						}}
					>
						{$i18n.t('Submit Assignment')}
					</button>
				{/if}
			</div>
		</div>
	{/if}

	{#if showMobileDraft}
		<div
			class="fixed inset-0 z-40 flex items-end bg-black/40 lg:hidden"
			on:click={() => (showMobileDraft = false)}
		>
			<div
				class="flex h-[78dvh] w-full flex-col rounded-t-3xl bg-stone-50"
				on:click|stopPropagation
			>
				<div class="border-b border-gray-200 bg-white px-5 py-4">
					<div class="flex items-start justify-between gap-4">
						<div class="min-w-0 flex-1">
							<div class="text-xs uppercase tracking-[0.18em] text-gray-500">
								{$i18n.t(isAssignment ? 'Assignment Writing' : '写作')}
							</div>
							<div class="text-sm font-semibold text-gray-900">
								{isAssignment ? assignment?.title : noteTitle}
							</div>
						</div>
						<button
							class="rounded-full border border-gray-300 px-3 py-1.5 text-sm"
							on:click={() => {
								showMobileDraft = false;
							}}
						>
							{$i18n.t('Close')}
						</button>
					</div>
				</div>
				<div class="min-h-0 flex-1 overflow-y-auto px-5 py-5">
					<RichTextInput
						bind:editor
						bind:value={noteJson}
						editable={!isReadOnly}
						json={true}
						placeholder={$i18n.t(isAssignment ? 'Write the final assignment here.' : 'Start writing...')}
						className="input-prose min-h-[60vh]"
						onChange={handleContentChange}
						on:paste={async (event) => {
							const clipboardEvent = event?.detail?.event ?? event;
							const payload =
								clipboardEvent?.clipboardData?.getData('application/x-openwebui-ai-snippet+json') ??
								'';
							if (!payload) {
								pendingSource = {
									sourceType: 'external_paste',
									sourceMessageId: null,
									text: ''
								};
								return;
							}
							try {
								const meta = JSON.parse(payload);
								pendingSource = {
									sourceType: meta.sourceType ?? 'ai_pasted',
									sourceMessageId: meta.sourceMessageId ?? null,
									text: meta.text ?? ''
								};
							} catch (error) {
								console.error(error);
							}
						}}
					/>
				</div>
			</div>
		</div>
	{/if}

	{#if isAssignment && showSubmitModal}
		<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
			<div class="w-full max-w-xl rounded-3xl bg-white p-6 shadow-2xl">
				<h2 class="text-xl font-semibold text-gray-900">
					{$i18n.t('Reflection Before Submitting Assignment')}
				</h2>
				<p class="mt-1 text-sm text-gray-500">
					{$i18n.t('Complete your reflection before submitting your assignment.')}
				</p>

				<div class="mt-5">
					<div class="mb-2 block text-sm font-medium text-gray-800">
						{$i18n.t('What did AI help you with? Select all that apply.')}
					</div>
					<div class="flex flex-wrap gap-2">
						{#each helpTypes as item}
							<button
								type="button"
								aria-pressed={aiHelpTypes.includes(item)}
								class={`rounded-full border px-3 py-2 text-sm transition ${
									aiHelpTypes.includes(item)
										? 'border-gray-900 bg-gray-900 text-white'
										: 'border-gray-300 bg-white text-gray-700 hover:border-gray-500'
								}`}
								on:click={() => toggleAiHelpType(item)}
							>
								{$i18n.t(item)}
							</button>
						{/each}
					</div>
				</div>

				<div class="mt-4">
					<label for="reflection-text" class="mb-2 block text-sm font-medium text-gray-800">
						{$i18n.t('How did you judge, revise, or reject AI suggestions?')}
					</label>
					{#if aiHelpTypes.includes('Other')}
						<div class="mb-3">
							<label for="other-ai-help-text" class="mb-2 block text-sm font-medium text-gray-800">
								请简单写一下 AI 还帮助了你什么。
							</label>
							<input
								id="other-ai-help-text"
								bind:value={otherAiHelpText}
								class="w-full rounded-2xl border border-gray-300 px-3 py-3 text-sm outline-none"
								placeholder="例如：帮我理解题目，或帮我整理论据。"
							/>
						</div>
					{/if}
					<textarea
						id="reflection-text"
						bind:value={reflectionText}
						class="min-h-40 w-full rounded-2xl border border-gray-300 px-3 py-3 text-sm outline-none"
						placeholder={$i18n.t('Recommended 50-100 characters. Minimum 30.')}
					></textarea>
				</div>

				<div class="mt-6 flex justify-end gap-3">
					<button
						class="rounded-full border border-gray-300 px-4 py-2 text-sm"
						on:click={() => {
							showSubmitModal = false;
						}}
					>
						{$i18n.t('Cancel')}
					</button>
					<button class="rounded-full bg-gray-900 px-4 py-2 text-sm text-white" on:click={submit}>
						{$i18n.t('Submit Assignment')}
					</button>
				</div>
			</div>
		</div>
	{/if}
{:else if loadError}
	<div class="mx-auto max-w-3xl px-4 py-16">
		<div class="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
			{loadError}
		</div>
	</div>
{/if}
