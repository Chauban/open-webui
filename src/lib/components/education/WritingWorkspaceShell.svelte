<script lang="ts">
	// @ts-nocheck
	import { getContext, onDestroy, onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import { mobile, selectedFolder } from '$lib/stores';

	import RichTextInput from '$lib/components/common/RichTextInput.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Chat from '$lib/components/chat/Chat.svelte';
	import ReviewResultCard from '$lib/components/education/ReviewResultCard.svelte';
	import SubmissionHistoryModal from '$lib/components/education/SubmissionHistoryModal.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import { EDU_FIELD_CLASS, eduSegmentClass } from '$lib/components/education/styles';
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
	let review = null;
	let effectiveDueAt = null;
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
	let isSubmitting = false;
	let showAssignmentDescription = false;
	let showSubmissionHistory = false;

	let nowTick = Date.now();
	let countdownIntervalId: ReturnType<typeof setInterval> | null = null;

	const MAX_SAVE_RETRIES = 3;
	const SAVE_RETRY_DELAYS_MS = [2000, 4000, 8000];
	let saveRetryAttempt = 0;
	let saveRetryTimer: ReturnType<typeof setTimeout> | null = null;
	let hasUnsavedFailure = false;

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
	$: activeDueAt = isAssignment ? (effectiveDueAt ?? assignment?.due_at ?? null) : null;
	$: isPastDue = activeDueAt ? activeDueAt * 1000 <= nowTick : false;
	// 已批改即定稿:只有老师退回(review_status 变回 returned)才重新解锁。
	$: isGraded = review?.review_status === 'reviewed';
	$: isReadOnly = isAssignment ? isPastDue || isGraded : false;
	$: canSubmitAssignment = isAssignment && !isPastDue && !isGraded;
	const getDefaultPersonalTitle = () => get(i18n).t('Untitled Writing');
	const normalizePersonalTitle = (value?: string | null) => {
		const normalized = value?.trim();
		if (!normalized || normalized === 'Untitled Writing') {
			return getDefaultPersonalTitle();
		}
		return normalized;
	};

	const DAY_SECONDS = 24 * 60 * 60;
	const HOUR_SECONDS = 60 * 60;

	// Mirrors the amber/gray urgency coloring already used on the /me/writing due-date
	// badges, with an added rose tier for the last hour before the deadline.
	const computeDueCountdown = (dueAtSeconds: number, nowMs: number) => {
		const remainingSeconds = dueAtSeconds - nowMs / 1000;

		if (remainingSeconds <= 0) {
			return { overdue: true, className: 'text-gray-500', labelKey: '', params: {} };
		}

		let className = 'text-gray-500';
		if (remainingSeconds < HOUR_SECONDS) {
			className = 'font-medium text-rose-600';
		} else if (remainingSeconds < DAY_SECONDS) {
			className = 'font-medium text-amber-600';
		}

		const totalMinutes = Math.max(1, Math.floor(remainingSeconds / 60));
		const days = Math.floor(totalMinutes / 1440);
		const hours = Math.floor((totalMinutes % 1440) / 60);
		const minutes = totalMinutes % 60;

		if (days >= 1) {
			return {
				overdue: false,
				className,
				labelKey: 'Due in {{days}}d {{hours}}h',
				params: { days, hours }
			};
		}
		if (hours >= 1) {
			return { overdue: false, className, labelKey: 'Due in {{hours}}h', params: { hours } };
		}
		return { overdue: false, className, labelKey: 'Due in {{minutes}}m', params: { minutes } };
	};

	$: isResubmitDeadline = review?.review_status === 'returned';
	$: formattedDueAt = effectiveDueAt ? new Date(effectiveDueAt * 1000).toLocaleString() : '';
	$: dueCountdown =
		isAssignment && effectiveDueAt ? computeDueCountdown(effectiveDueAt, nowTick) : null;
	$: dueLabelKey = isResubmitDeadline ? 'Resubmit before' : 'Due At';
	$: dueColorClass = isResubmitDeadline
		? 'font-medium text-rose-600'
		: (dueCountdown?.className ?? 'text-gray-500');

	$: saveStatusDisplay =
		saveStatusKey === 'Retrying...' && saveRetryAttempt > 0
			? `${$i18n.t('Retrying...')} (${saveRetryAttempt}/${MAX_SAVE_RETRIES})`
			: $i18n.t(saveStatusKey);

	$: if (!aiHelpTypes.includes('Other') && otherAiHelpText) {
		otherAiHelpText = '';
	}

	const getSubmitReflectionText = () => {
		const baseReflection = reflectionText.trim();
		if (!aiHelpTypes.includes('Other')) {
			return baseReflection;
		}

		const otherDetail = otherAiHelpText.trim();
		return `${$i18n.t('Other help: {{detail}}', { detail: otherDetail })}\n\n${baseReflection}`.trim();
	};

	const toggleAiHelpType = (helpType: string) => {
		aiHelpTypes = aiHelpTypes.includes(helpType)
			? aiHelpTypes.filter((item) => item !== helpType)
			: [...aiHelpTypes, helpType];
		saveReflectionDraft(reflectionText, otherAiHelpText);
	};

	const getReflectionDraftKey = () => `education:reflection-draft:${assignment?.id ?? ''}`;

	const loadReflectionDraft = () => {
		if (!isAssignment || !assignment?.id) return;
		try {
			const raw = localStorage.getItem(getReflectionDraftKey());
			if (!raw) return;
			const draft = JSON.parse(raw);
			reflectionText = draft?.reflectionText ?? reflectionText;
			otherAiHelpText = draft?.otherAiHelpText ?? otherAiHelpText;
			if (Array.isArray(draft?.aiHelpTypes) && draft.aiHelpTypes.length > 0) {
				aiHelpTypes = draft.aiHelpTypes;
			}
		} catch (error) {
			console.error(error);
		}
	};

	const saveReflectionDraft = (reflection: string, otherHelp: string) => {
		if (!isAssignment || !assignment?.id) return;
		try {
			localStorage.setItem(
				getReflectionDraftKey(),
				JSON.stringify({ reflectionText: reflection, otherAiHelpText: otherHelp, aiHelpTypes })
			);
		} catch (error) {
			console.error(error);
		}
	};

	const clearReflectionDraft = () => {
		if (!isAssignment || !assignment?.id) return;
		try {
			localStorage.removeItem(getReflectionDraftKey());
		} catch (error) {
			console.error(error);
		}
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
			autoSaveTimer = null;
			void persistDraft('autosave');
		}, 1200);
	};

	const performPersistDraft = async (triggerType = 'autosave') => {
		if (!writingSession || isReadOnly) return;
		saving = true;
		hasUnsavedFailure = false;
		saveRetryAttempt = 0;
		saveStatusKey = 'Saving...';

		let version = null;
		for (let attempt = 0; attempt <= MAX_SAVE_RETRIES; attempt += 1) {
			try {
				await autosaveWritingSession(localStorage.token, writingSession.id, {
					content_json: noteJson,
					content_html: noteHtml,
					content_text: noteText,
					save_reason: triggerType
				});

				if (!version) {
					version = await createWritingVersion(localStorage.token, writingSession.id, {
						trigger_type: triggerType,
						content_json: noteJson,
						content_text: noteText
					});
				}

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
				hasUnsavedFailure = false;
				saveRetryAttempt = 0;
				saving = false;
				return;
			} catch (error) {
				console.error(error);

				if (attempt >= MAX_SAVE_RETRIES) {
					hasUnsavedFailure = true;
					saveStatusKey = 'Save failed';
					saveRetryAttempt = 0;
					saving = false;
					return;
				}

				saveRetryAttempt = attempt + 1;
				saveStatusKey = 'Retrying...';
				await new Promise((resolve) => {
					saveRetryTimer = setTimeout(resolve, SAVE_RETRY_DELAYS_MS[attempt]);
				});
				saveRetryTimer = null;
			}
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
		if (!canSubmitAssignment || isSubmitting) return;
		if (aiHelpTypes.length === 0) {
			toast.error($i18n.t('Select at least one AI help type.'));
			return;
		}
		if (aiHelpTypes.includes('Other') && otherAiHelpText.trim().length === 0) {
			toast.error($i18n.t('Please add a short note about what else AI helped with.'));
			return;
		}

		const submitReflectionText = getSubmitReflectionText();
		if (submitReflectionText.length < 30) {
			toast.error($i18n.t('Reflection must be at least 30 characters.'));
			return;
		}

		isSubmitting = true;
		try {
			await persistDraft('submit_preflight', { force: true });

			await submitAssignment(localStorage.token, assignment.id, {
				writing_session_id: writingSession.id,
				final_content_json: noteJson,
				final_content_html: noteHtml,
				final_content_text: noteText,
				ai_help_types: aiHelpTypes,
				reflection_text: submitReflectionText
			});
			clearReflectionDraft();
			await load();
			toast.success($i18n.t('Assignment submitted'));
			await goto('/me/writing');
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			isSubmitting = false;
		}
	};

	const load = async () => {
		try {
			const workspace = await loadWorkspace();
			assignment = workspace.assignment ?? null;
			review = workspace.review ?? null;
			effectiveDueAt = workspace.effective_due_at ?? null;
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

	onMount(() => {
		void load();
		if (isAssignment) {
			countdownIntervalId = setInterval(() => {
				nowTick = Date.now();
			}, 60000);
		}
	});

	onDestroy(() => {
		if (
			$selectedFolder?.meta?.mode === 'assignment_writing' ||
			$selectedFolder?.meta?.mode === 'personal_writing' ||
			$selectedFolder?.meta?.category === 'assignment_project' ||
			$selectedFolder?.meta?.category === 'personal_writing'
		) {
			selectedFolder.set(null);
		}
		if (countdownIntervalId) clearInterval(countdownIntervalId);

		// beforeunload 只能拦住关闭/刷新,拦不住 SvelteKit 客户端路由跳转,
		// 所以销毁前要把防抖窗口内的最后一次编辑补交,否则这段编辑会丢。
		const hasPendingDraft = autoSaveTimer !== null || unsavedOperations.length > 0;
		if (autoSaveTimer) clearTimeout(autoSaveTimer);
		if (saveRetryTimer) clearTimeout(saveRetryTimer);
		if (hasPendingDraft) {
			void persistDraft('autosave');
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

<svelte:window
	on:beforeunload={(event) => {
		if (autoSaveTimer || saving || hasUnsavedFailure) {
			event.preventDefault();
			event.returnValue = '';
		}
	}}
/>

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
							{$i18n.t(isAssignment ? 'Assignment Writing' : 'Writing')}
						</div>
						{#if isAssignment}
							<div class="text-sm font-semibold text-gray-900">{assignment?.title}</div>
							<div class="text-xs text-gray-500">
								{#if isGraded}
									{$i18n.t('Graded. Ask your teacher to return it if you need to revise.')}
								{:else if isPastDue}
									{$i18n.t('Submitted assignments stay available for review in read-only mode.')}
								{:else if isSubmitted}
									{$i18n.t('Submitted. You can revise and resubmit before the deadline.')}
								{:else}
									{$i18n.t('Track typed text, AI insertions, and in-app AI paste.')}
								{/if}
							</div>
							{#if effectiveDueAt}
								<div class="mt-1 text-xs {dueColorClass}">
									{#if !isResubmitDeadline && dueCountdown?.overdue}
										{$i18n.t('Overdue')}
									{:else}
										{$i18n.t(dueLabelKey)}: {formattedDueAt}
										{#if dueCountdown?.overdue}
											· {$i18n.t('Overdue')}
										{:else if dueCountdown}
											· {$i18n.t(dueCountdown.labelKey, dueCountdown.params)}
										{/if}
									{/if}
								</div>
							{/if}
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
						{#if isAssignment && review}
							<button
								class="rounded-full border border-gray-200 px-3 py-1 text-xs text-gray-600 hover:bg-stone-100"
								on:click={() => (showSubmissionHistory = true)}
							>
								{$i18n.t('Submission History')}
							</button>
						{/if}
						<div class="rounded-full bg-stone-100 px-3 py-1 text-xs text-gray-600">
							{saveStatusDisplay}
						</div>
						{#if canSubmitAssignment}
							<button
								class="rounded-full bg-gray-900 px-4 py-2 text-sm text-white"
								on:click={() => {
									loadReflectionDraft();
									showSubmitModal = true;
								}}
							>
								{$i18n.t('Submit Assignment')}
							</button>
						{/if}
					</div>
				</div>
				{#if isAssignment && assignment?.description}
					<div class="mt-3">
						<button
							type="button"
							class="text-xs font-medium text-gray-500 hover:text-gray-700 hover:underline"
							on:click={() => (showAssignmentDescription = !showAssignmentDescription)}
						>
							{$i18n.t(
								showAssignmentDescription
									? 'Hide assignment requirements'
									: 'View assignment requirements'
							)}
						</button>
						{#if showAssignmentDescription}
							<div class="mt-2 whitespace-pre-wrap rounded-2xl bg-stone-50 p-3 text-xs text-gray-600">
								{assignment.description}
							</div>
						{/if}
					</div>
				{/if}
			</div>
			<div class="min-h-0 flex-1 overflow-y-auto px-5 py-5">
				{#if isAssignment && review}
					<ReviewResultCard {review} onRevise={null} />
				{/if}
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
					{saveStatusDisplay}
				</div>
				<EduButton
					size="sm"
					on:click={() => {
						showMobileDraft = true;
					}}
				>
					{$i18n.t(isAssignment ? 'Assignment Content' : 'Writing Content')}
				</EduButton>
				{#if canSubmitAssignment}
					<EduButton
						variant="primary"
						size="sm"
						on:click={() => {
							loadReflectionDraft();
							showSubmitModal = true;
						}}
					>
						{$i18n.t('Submit Assignment')}
					</EduButton>
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
								{$i18n.t(isAssignment ? 'Assignment Writing' : 'Writing')}
							</div>
							<div class="text-sm font-semibold text-gray-900">
								{isAssignment ? assignment?.title : noteTitle}
							</div>
						</div>
						<EduButton
							size="sm"
							on:click={() => {
								showMobileDraft = false;
							}}
						>
							{$i18n.t('Close')}
						</EduButton>
					</div>
				</div>
				<div class="min-h-0 flex-1 overflow-y-auto px-5 py-5">
					{#if isAssignment && review}
						<ReviewResultCard {review} onRevise={null} />
					{/if}
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

	{#if isAssignment && assignment}
		<SubmissionHistoryModal bind:show={showSubmissionHistory} assignmentId={assignment.id} />
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
								class={eduSegmentClass(aiHelpTypes.includes(item))}
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
								{$i18n.t('Please briefly describe what else AI helped with.')}
							</label>
							<input
								id="other-ai-help-text"
								bind:value={otherAiHelpText}
								on:input={() => saveReflectionDraft(reflectionText, otherAiHelpText)}
								class="w-full {EDU_FIELD_CLASS}"
								placeholder={$i18n.t(
									'For example: helping me understand the topic or organize evidence.'
								)}
							/>
							{#if otherAiHelpText.trim().length === 0}
								<div class="mt-1 text-xs text-rose-600">
									{$i18n.t('Please add a short note about what else AI helped with.')}
								</div>
							{/if}
						</div>
					{/if}
					<textarea
						id="reflection-text"
						bind:value={reflectionText}
						on:input={() => saveReflectionDraft(reflectionText, otherAiHelpText)}
						class="min-h-40 w-full {EDU_FIELD_CLASS}"
						placeholder={$i18n.t('Recommended 50-100 characters. Minimum 30.')}
					></textarea>
					<div
						class="mt-1 flex justify-end text-xs {reflectionText.trim().length < 30
							? 'text-rose-600'
							: 'text-gray-400'}"
					>
						{$i18n.t('{{count}} / {{min}} characters (minimum)', {
							count: reflectionText.trim().length,
							min: 30
						})}
					</div>
				</div>

				<div class="mt-6 flex justify-end gap-3">
					<EduButton
						on:click={() => {
							showSubmitModal = false;
						}}
					>
						{$i18n.t('Cancel')}
					</EduButton>
					<EduButton
						variant="primary"
						class="flex items-center gap-2 disabled:cursor-not-allowed"
						disabled={isSubmitting}
						on:click={submit}
					>
						{#if isSubmitting}
							<Spinner className="size-4" />
							{$i18n.t('Submitting...')}
						{:else}
							{$i18n.t('Submit Assignment')}
						{/if}
					</EduButton>
				</div>
			</div>
		</div>
	{/if}
{:else if loadError}
	<div class="mx-auto max-w-3xl px-4 py-16">
		<EduStateCard tone="error">{loadError}</EduStateCard>
	</div>
{/if}
