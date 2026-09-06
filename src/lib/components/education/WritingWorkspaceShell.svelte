<script lang="ts">
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
	import WritingComposition from '$lib/components/education/WritingComposition.svelte';
	import SubmissionHistoryModal from '$lib/components/education/SubmissionHistoryModal.svelte';
	import AssignmentBrief from '$lib/components/education/AssignmentBrief.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import { EDU_FIELD_CLASS, eduSegmentClass } from '$lib/components/education/styles';
	import { prepareAssistantContentForWriting } from '$lib/utils/writing-content';
	import { createSerializedSaveRunner } from '$lib/utils/save-coordinator';
	import { getStructuredReflectionError } from '$lib/utils/structured-reflection';
	import { formatEpoch, resolveErrorMessage } from '$lib/utils/education';
	import {
		applySourceMapChange,
		normalizeSourceRuns,
		provenanceSegmentsToSourceRuns,
		sourceRunsToProvenanceSegments
	} from '$lib/utils/writing-source-map';
	import type { SourceRun } from '$lib/utils/writing-source-map';
	import {
		autosaveWritingSession,
		createEditorOperations,
		createProvenanceSegments,
		createWritingVersion,
		getWritingProcessSummary,
		setWritingSessionActiveChat,
		submitAssignment
	} from '$lib/apis/education';
	import { updateFolderById } from '$lib/apis/folders';
	import { updateNoteById } from '$lib/apis/notes';

	export let scope: 'assignment' | 'personal' = 'assignment';
	export let projectBaseUrl = '/me/writing';
	export let loadWorkspace: () => Promise<any>;

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

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
	let showSubmissionHistory = false;

	let nowTick = Date.now();
	let countdownIntervalId: ReturnType<typeof setInterval> | null = null;

	const MAX_SAVE_RETRIES = 3;
	const SAVE_RETRY_DELAYS_MS = [2000, 4000, 8000];
	let saveRetryAttempt = 0;
	let saveRetryTimer: ReturnType<typeof setTimeout> | null = null;
	let hasUnsavedFailure = false;

	let aiUsage: 'used' | 'none' | null = null;
	let aiHelpTypes = [];
	let otherAiHelpText = '';
	let reflectionAction = '';
	let reflectionLocation = '';
	let reflectionJudgement = '';
	let reflectionNextStep = '';

	let lastText = '';
	// 最近一次真正落成版本的正文，用来跳过「内容没变」的自动保存。
	let lastVersionedText = '';
	let pendingSource: null | { sourceType: string; sourceMessageId?: string | null; text?: string } =
		null;
	let sourceRuns: SourceRun[] = [];
	let clarificationAnsweredCount: number | null = null;
	let processSummaryRequest = 0;

	const refreshProcessSummary = async () => {
		if (!writingSession) return;
		const request = ++processSummaryRequest;
		try {
			const summary = await getWritingProcessSummary(localStorage.token, writingSession.id);
			if (request === processSummaryRequest) {
				clarificationAnsweredCount = summary.clarification_answered_count;
			}
		} catch (error) {
			if (request === processSummaryRequest) clarificationAnsweredCount = null;
			console.error(error);
		}
	};
	let unsavedOperations = [];
	let clientOperationSequence = 0;
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
			return {
				overdue: true,
				className: 'text-gray-500 dark:text-gray-400',
				labelKey: '',
				params: {}
			};
		}

		let className = 'text-gray-500 dark:text-gray-400';
		if (remainingSeconds < HOUR_SECONDS) {
			className = 'font-medium text-rose-600 dark:text-rose-400';
		} else if (remainingSeconds < DAY_SECONDS) {
			className = 'font-medium text-amber-600 dark:text-amber-400';
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
	$: formattedDueAt = formatEpoch(effectiveDueAt);
	$: dueCountdown =
		isAssignment && effectiveDueAt ? computeDueCountdown(effectiveDueAt, nowTick) : null;
	$: dueLabelKey = isResubmitDeadline ? 'Resubmit before' : 'Due At';
	$: dueColorClass = isResubmitDeadline
		? 'font-medium text-rose-600 dark:text-rose-400'
		: (dueCountdown?.className ?? 'text-gray-500 dark:text-gray-400');

	$: saveStatusDisplay =
		saveStatusKey === 'Retrying...' && saveRetryAttempt > 0
			? `${$i18n.t('Retrying...')} (${saveRetryAttempt}/${MAX_SAVE_RETRIES})`
			: $i18n.t(saveStatusKey);

	$: if (!aiHelpTypes.includes('Other') && otherAiHelpText) {
		otherAiHelpText = '';
	}
	$: if (aiUsage !== 'used' && aiHelpTypes.length > 0) {
		aiHelpTypes = [];
	}

	const toggleAiHelpType = (helpType: string) => {
		aiHelpTypes = aiHelpTypes.includes(helpType)
			? aiHelpTypes.filter((item) => item !== helpType)
			: [...aiHelpTypes, helpType];
		saveReflectionDraft();
	};

	const selectAiUsage = (value: 'used' | 'none') => {
		aiUsage = value;
		if (value === 'none') {
			aiHelpTypes = [];
			otherAiHelpText = '';
		}
		saveReflectionDraft();
	};

	const getReflectionDraftKey = () => `education:reflection-draft:${assignment?.id ?? ''}`;

	const loadReflectionDraft = () => {
		if (!isAssignment || !assignment?.id) return;
		try {
			const raw = localStorage.getItem(getReflectionDraftKey());
			if (!raw) return;
			const draft = JSON.parse(raw);
			reflectionAction = draft?.reflectionAction ?? '';
			reflectionLocation = draft?.reflectionLocation ?? '';
			reflectionJudgement = draft?.reflectionJudgement ?? '';
			reflectionNextStep = draft?.reflectionNextStep ?? '';
			otherAiHelpText = draft?.otherAiHelpText ?? otherAiHelpText;
			aiUsage = draft?.aiUsage === 'used' || draft?.aiUsage === 'none' ? draft.aiUsage : null;
			aiHelpTypes = Array.isArray(draft?.aiHelpTypes) ? draft.aiHelpTypes : [];
			if (aiUsage == null && aiHelpTypes.length > 0) aiUsage = 'used';
		} catch (error) {
			console.error(error);
		}
	};

	const saveReflectionDraft = () => {
		if (!isAssignment || !assignment?.id) return;
		try {
			localStorage.setItem(
				getReflectionDraftKey(),
				JSON.stringify({
					reflectionAction,
					reflectionLocation,
					reflectionJudgement,
					reflectionNextStep,
					otherAiHelpText,
					aiUsage,
					aiHelpTypes
				})
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
		unsavedOperations = [
			...unsavedOperations,
			{
				...operation,
				occurred_at_ms: Date.now(),
				client_sequence: clientOperationSequence++
			}
		];
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

				// 正文没变就不要再存一版。编辑器在选区/格式变化时也会触发 onChange，
				// 照存的话一篇稿子能攒出两百多个一模一样的版本：既撑大版本历史让老师
				// 没法看，也让「改了几版」这类过程指标彻底失去意义。
				// 提交类快照（submit / submit_preflight）必须留痕，不受此限。
				const isAutosave = triggerType === 'autosave';
				if (!version && (!isAutosave || noteText !== lastVersionedText)) {
					version = await createWritingVersion(localStorage.token, writingSession.id, {
						trigger_type: triggerType,
						content_json: noteJson,
						content_text: noteText
					});
					lastVersionedText = noteText;
				}

				if (unsavedOperations.length > 0) {
					await createEditorOperations(localStorage.token, writingSession.id, {
						operations: unsavedOperations
					});
					unsavedOperations = [];
				}

				// 正文没变时不会开新版本，来源分布同样没变，不必重写 source map。
				if (version) {
					await createProvenanceSegments(localStorage.token, writingSession.id, {
						version_id: version.id,
						replace_existing: true,
						segments: sourceRunsToProvenanceSegments(noteText, sourceRuns)
					});
				}

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
		// 两类事件都不是学生在改稿，必须一起挡掉：
		// docChanged=false 是选区/格式变化，正文一个字没动；
		// programmatic 是本组件自己把正文灌进编辑器（挂载和每次 value 同步）。
		// 灌入前编辑器是空文档，ProseMirror 照样报 docChanged=true，
		// 只看 docChanged 会把它当成学生清空全文：整篇记一次删除、source map
		// 被清掉，回填后又整体标成 user_typed，还会喂出假的「疑似未标注导入」。
		// 挡掉这两类之后，剩下的空文档就真是学生全选删光，如实留痕。
		if (isReadOnly || !content.docChanged || content.programmatic) return;
		const nextText = content.text ?? content.md ?? '';

		noteJson = content.json;
		noteHtml = content.html;
		noteText = nextText;
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
			else if (
				sourceType === 'ai_pasted' ||
				sourceType === 'external_paste' ||
				sourceType === 'paste'
			) {
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
		if (aiUsage == null) {
			toast.error($i18n.t('Choose whether AI was used.'));
			return;
		}
		if (aiUsage === 'used' && aiHelpTypes.length === 0) {
			toast.error($i18n.t('Select at least one AI help type.'));
			return;
		}
		if (aiHelpTypes.includes('Other') && otherAiHelpText.trim().length === 0) {
			toast.error($i18n.t('Please add a short note about what else AI helped with.'));
			return;
		}

		const reflectionError = getStructuredReflectionError({
			action: reflectionAction,
			location: reflectionLocation,
			judgement: reflectionJudgement,
			next_step: reflectionNextStep
		});
		if (reflectionError) {
			toast.error($i18n.t(reflectionError));
			return;
		}

		isSubmitting = true;
		try {
			await persistDraft('submit_preflight', { force: true });
			if (hasUnsavedFailure) {
				toast.error($i18n.t('Save failed. Fix the connection before submitting.'));
				return;
			}

			await submitAssignment(localStorage.token, assignment.id, {
				writing_session_id: writingSession.id,
				final_content_json: noteJson,
				final_content_html: noteHtml,
				final_content_text: noteText,
				ai_used: aiUsage === 'used',
				ai_help_types: aiHelpTypes,
				data_completeness: {
					version_data_complete: true,
					editor_operations_complete: true,
					source_tracking_complete: true
				},
				reflection: {
					action: reflectionAction.trim(),
					location: reflectionLocation.trim(),
					judgement: reflectionJudgement.trim(),
					next_step: reflectionNextStep.trim(),
					other_ai_help: aiHelpTypes.includes('Other') ? otherAiHelpText.trim() : null
				}
			});
			clearReflectionDraft();
			await load();
			toast.success($i18n.t('Assignment submitted'));
			await goto('/me/writing');
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
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
			void refreshProcessSummary();
			workspaceProject = workspace.project;
			workspaceNote = workspace.note;
			isSubmitted = workspace.writing_session?.status === 'submitted';
			saveStatusKey = isSubmitted ? 'Submitted' : 'Saved';
			noteJson = workspace.note?.data?.content?.json ?? null;
			noteHtml = workspace.note?.data?.content?.html ?? '';
			noteText = workspace.note?.data?.content?.md ?? '';
			noteTitle = normalizePersonalTitle(workspace.note?.title);
			lastText = noteText;
			lastVersionedText = noteText;
			sourceRuns = workspace.source_map?.length
				? provenanceSegmentsToSourceRuns(noteText, workspace.source_map)
				: normalizeSourceRuns([], noteText.length);
			currentChatId = $page.url.searchParams.get('chat') ?? '';
			await selectedFolder.set(workspaceProject);
			loaded = true;
		} catch (error) {
			loadError = resolveErrorMessage(error, t);
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

	$: if (
		loaded &&
		writingSession?.id &&
		currentChatId &&
		lastPersistedActiveChatId !== currentChatId
	) {
		lastPersistedActiveChatId = currentChatId;
		void setWritingSessionActiveChat(
			localStorage.token,
			writingSession.id,
			currentChatId || null
		).catch((error) => {
			console.error(error);
		});
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
		{projectBaseUrl}
		responseInsertHandler={isReadOnly ? null : insertAssistantContent}
		responseCopyHandler={copyAssistantContentWithSource}
		onToolCallCompleted={() => void refreshProcessSummary()}
		responseInsertLabel={'Insert to Writing'}
		readOnly={isReadOnly}
		disableContextActions={false}
		allowAssignmentWorkspaceChat={isAssignment}
		showRightPanel={!$mobile}
		rightPanelWidth={520}
		rightPanelMinWidth={400}
		rightPanelClassName="hidden lg:flex"
	>
		<div
			slot="right-panel"
			class="h-full w-full flex-col border-l border-gray-200 dark:border-gray-800 bg-stone-50 dark:bg-gray-900 lg:flex"
		>
			<div
				class="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 px-5 py-4"
			>
				<div class="flex items-start justify-between gap-4">
					<div class="min-w-0 flex-1">
						<div class="text-xs uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
							{$i18n.t(isAssignment ? 'Assignment Writing' : 'Writing')}
						</div>
						{#if isAssignment}
							<div class="text-sm font-semibold text-gray-900 dark:text-gray-100">
								{assignment?.title}
							</div>
							<div class="text-xs text-gray-500 dark:text-gray-400">
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
								class="mt-1 w-full rounded-2xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-sm font-semibold text-gray-900 dark:text-gray-100 outline-none"
								placeholder={$i18n.t('Untitled Writing')}
								on:blur={saveTitle}
							/>
							<div class="mt-1 text-xs text-gray-500 dark:text-gray-400">
								{$i18n.t('Write freely. Autosaved.')}
							</div>
						{/if}
					</div>
					<div class="flex items-center gap-2">
						{#if isSubmitted}
							<div
								class="rounded-full bg-emerald-100 px-3 py-1 text-xs text-emerald-700 dark:text-emerald-300"
							>
								{$i18n.t('Submitted')}
							</div>
						{/if}
						{#if isAssignment && review}
							<button
								class="rounded-full border border-gray-200 dark:border-gray-800 px-3 py-1 text-xs text-gray-600 dark:text-gray-400 hover:bg-stone-100 dark:hover:bg-gray-800"
								on:click={() => (showSubmissionHistory = true)}
							>
								{$i18n.t('Submission History')}
							</button>
						{/if}
						<div
							class="rounded-full bg-stone-100 dark:bg-gray-800 px-3 py-1 text-xs text-gray-600 dark:text-gray-400"
						>
							{saveStatusDisplay}
						</div>
						{#if canSubmitAssignment}
							<EduButton
								variant="primary"
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
				{#if isAssignment}
					<AssignmentBrief {assignment} />
				{/if}
			</div>
			<div class="min-h-0 flex-1 overflow-y-auto px-5 py-5">
				{#if isAssignment && review}
					<ReviewResultCard {review} {assignment} onRevise={null} />
				{/if}
				<WritingComposition {sourceRuns} {clarificationAnsweredCount} />
				<RichTextInput
					bind:editor
					bind:value={noteJson}
					editable={!isReadOnly}
					json={true}
					placeholder={$i18n.t(
						isAssignment ? 'Write the final assignment here.' : 'Start writing...'
					)}
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
				class="pointer-events-auto flex items-center gap-2 rounded-full border border-gray-200 dark:border-gray-800 bg-white/95 dark:bg-gray-850/95 px-3 py-2 shadow-lg backdrop-blur"
			>
				<div
					class="rounded-full bg-stone-100 dark:bg-gray-800 px-3 py-1 text-xs text-gray-600 dark:text-gray-400"
				>
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
				class="flex h-[78dvh] w-full flex-col rounded-t-3xl bg-stone-50 dark:bg-gray-900"
				on:click|stopPropagation
			>
				<div
					class="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 px-5 py-4"
				>
					<div class="flex items-start justify-between gap-4">
						<div class="min-w-0 flex-1">
							<div class="text-xs uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
								{$i18n.t(isAssignment ? 'Assignment Writing' : 'Writing')}
							</div>
							<div class="text-sm font-semibold text-gray-900 dark:text-gray-100">
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
					{#if isAssignment}
						<AssignmentBrief {assignment} />
					{/if}
				</div>
				<div class="min-h-0 flex-1 overflow-y-auto px-5 py-5">
					{#if isAssignment && review}
						<ReviewResultCard {review} {assignment} onRevise={null} />
					{/if}
					<WritingComposition {sourceRuns} {clarificationAnsweredCount} />
					<RichTextInput
						bind:editor
						bind:value={noteJson}
						editable={!isReadOnly}
						json={true}
						placeholder={$i18n.t(
							isAssignment ? 'Write the final assignment here.' : 'Start writing...'
						)}
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
		<SubmissionHistoryModal bind:show={showSubmissionHistory} {assignment} />
	{/if}

	{#if isAssignment && showSubmitModal}
		<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
			<div class="w-full max-w-xl rounded-3xl bg-white dark:bg-gray-850 p-6 shadow-2xl">
				<h2 class="text-xl font-semibold text-gray-900 dark:text-gray-100">
					{$i18n.t('Reflection Before Submitting Assignment')}
				</h2>
				<p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
					{$i18n.t('Complete your reflection before submitting your assignment.')}
				</p>

				<div class="mt-5">
					<div class="mb-2 block text-sm font-medium text-gray-800 dark:text-gray-200">
						{$i18n.t('Did you use AI for this submission?')}
					</div>
					<div class="flex flex-wrap gap-2">
						<button
							type="button"
							aria-pressed={aiUsage === 'used'}
							class={eduSegmentClass(aiUsage === 'used')}
							on:click={() => selectAiUsage('used')}
						>
							{$i18n.t('Used AI')}
						</button>
						<button
							type="button"
							aria-pressed={aiUsage === 'none'}
							class={eduSegmentClass(aiUsage === 'none')}
							on:click={() => selectAiUsage('none')}
						>
							{$i18n.t('Did not use AI')}
						</button>
					</div>
					{#if aiUsage === 'used'}
						<div class="mb-2 mt-4 block text-sm font-medium text-gray-800 dark:text-gray-200">
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
					{/if}
				</div>

				<div class="mt-4 space-y-4">
					{#if aiHelpTypes.includes('Other')}
						<div>
							<label
								for="other-ai-help-text"
								class="mb-2 block text-sm font-medium text-gray-800 dark:text-gray-200"
							>
								{$i18n.t('Please briefly describe what else AI helped with.')}
							</label>
							<input
								id="other-ai-help-text"
								bind:value={otherAiHelpText}
								on:input={saveReflectionDraft}
								class="w-full {EDU_FIELD_CLASS}"
								placeholder={$i18n.t(
									'For example: helping me understand the topic or organize evidence.'
								)}
							/>
							{#if otherAiHelpText.trim().length === 0}
								<div class="mt-1 text-xs text-rose-600 dark:text-rose-400">
									{$i18n.t('Please add a short note about what else AI helped with.')}
								</div>
							{/if}
						</div>
					{/if}
					<div>
						<label
							for="reflection-action"
							class="mb-2 block text-sm font-medium text-gray-800 dark:text-gray-200"
						>
							{$i18n.t('What did you change?')}
						</label>
						<textarea
							id="reflection-action"
							bind:value={reflectionAction}
							on:input={saveReflectionDraft}
							class="min-h-20 w-full {EDU_FIELD_CLASS}"
							placeholder={$i18n.t('Describe the concrete revision you made.')}
						></textarea>
					</div>
					<div>
						<label
							for="reflection-location"
							class="mb-2 block text-sm font-medium text-gray-800 dark:text-gray-200"
						>
							{$i18n.t('Where did you make this change?')}
						</label>
						<input
							id="reflection-location"
							bind:value={reflectionLocation}
							on:input={saveReflectionDraft}
							class="w-full {EDU_FIELD_CLASS}"
							placeholder={$i18n.t(
								'For example: paragraph 2, the conclusion, or the evidence section.'
							)}
						/>
					</div>
					<div>
						<label
							for="reflection-judgement"
							class="mb-2 block text-sm font-medium text-gray-800 dark:text-gray-200"
						>
							{$i18n.t('Why did you make this judgement?')}
						</label>
						<textarea
							id="reflection-judgement"
							bind:value={reflectionJudgement}
							on:input={saveReflectionDraft}
							class="min-h-20 w-full {EDU_FIELD_CLASS}"
							placeholder={$i18n.t(
								'Explain why you accepted, rejected, or changed the suggestion or feedback.'
							)}
						></textarea>
					</div>
					<div>
						<label
							for="reflection-next-step"
							class="mb-2 block text-sm font-medium text-gray-800 dark:text-gray-200"
						>
							{$i18n.t('What will you do next time?')}
						</label>
						<textarea
							id="reflection-next-step"
							bind:value={reflectionNextStep}
							on:input={saveReflectionDraft}
							class="min-h-20 w-full {EDU_FIELD_CLASS}"
							placeholder={$i18n.t('Write one concrete action for your next assignment.')}
						></textarea>
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
