<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import {
		deleteAssignment,
		setAssignmentVisibility,
		getTeacherAssignment,
		getTeacherAssignmentDefaults,
		getTeacherClassrooms,
		getTeacherReflectionQuestionSets,
		updateAssignment
	} from '$lib/apis/education';
	import type {
		ReflectionQuestionSet,
		ThinkingControl,
		ThinkingSetting
	} from '$lib/apis/education';
	import AssignmentAiSummary from '$lib/components/education/AssignmentAiSummary.svelte';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import AssignmentForm from '$lib/components/education/AssignmentForm.svelte';
	import AssignmentChangeReason from '$lib/components/education/AssignmentChangeReason.svelte';
	import TeachingPreparationPanel from '$lib/components/education/TeachingPreparationPanel.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import { taskTypeLabel } from '$lib/utils/task-types';
	import { THINKING_SETTING_TEXT } from '$lib/utils/ai-steps';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import { assignmentTabs } from '$lib/components/education/teacher-nav';
	import {
		buildAssignmentPayload,
		draftThinkingFrom,
		type AssignmentDraft
	} from '$lib/utils/assignment-form';
	import { resolveErrorMessage, toLocalDateTimeInput } from '$lib/utils/education';

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	const assignmentId = $page.params.assignmentId;

	let allowedTaskModes: import('$lib/apis/education').TaskMode[] = [];
	let photoTranscriptionModel: import('$lib/apis/education').ImageParsingModelView | null = null;
	let imageParsingModel: import('$lib/apis/education').ImageParsingModelView | null = null;
	let teachingConfigs: Partial<
		Record<import('$lib/apis/education').TaskMode, import('$lib/apis/education').TeachingConfig>
	> = {};
	let changeSummary = '';
	let showSaveConfirm = false;
	let pendingPayload: Parameters<typeof updateAssignment>[2] | null = null;
	let changePreview: Array<{ label: string; before: string; after: string }> = [];
	let adoptLatest = false;
	let item = null;
	let classrooms = [];
	let reflectionQuestionSets: ReflectionQuestionSet[] = [];
	let draft: AssignmentDraft | null = null;
	let classroomId = '';
	let loading = true;
	let loadError = '';
	let saving = false;
	let changingVisibility = false;
	const toggleVisibility = async () => {
		if (changingVisibility) return;
		changingVisibility = true;
		try {
			const assignment = await setAssignmentVisibility(
				localStorage.token,
				assignmentId,
				!item.assignment.hidden
			);
			item = { ...item, assignment };
			toast.success(
				t(assignment.hidden ? 'Assignment hidden.' : 'Assignment visible to students.')
			);
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			changingVisibility = false;
		}
	};
	let saveError = '';
	let showDeleteConfirm = false;
	let thinkingPolicy: { control: ThinkingControl; default: ThinkingSetting } | null = null;
	// 保存后让 AI 设置卡重新读取生效值。
	let aiSummaryVersion = 0;

	$: hasSubmissions = (item?.submission_count ?? 0) > 0;

	const syncDraft = () => {
		const assignment = item.assignment;
		classroomId = assignment.classroom_id || '';
		draft = {
			scoringMode: assignment.scoring_mode,
			title: assignment.title || '',
			description: assignment.description || '',
			dueAt: assignment.due_at ? toLocalDateTimeInput(assignment.due_at) : '',
			scoreMax: String(assignment.score_max),
			coachingStyle: assignment.coaching_style,
			taskMode: assignment.task_mode,
			photoTranscriptionEnabled: assignment.photo_transcription_enabled,
			imageReadingEnabled: assignment.image_reading_enabled,
			challengeEnabled: assignment.challenge_enabled ?? false,
			challengeRounds: assignment.challenge_rounds ?? 3,
			challengeFocusKeys: [...(assignment.challenge_focus_keys ?? [])],
			reflectionQuestions: (assignment.reflection_questions ?? []).map((question) => ({
				...question,
				options: [...question.options]
			})),
			rubricCriteria: assignment.rubric_schema.criteria.map((criterion) => ({
				key: criterion.key,
				label: criterion.label,
				maxScore: String(criterion.max_score)
			})),
			...draftThinkingFrom(assignment.model_params)
		};
	};

	const loadData = async () => {
		const [assignmentItem, teacherClassrooms, questionSets, assignmentDefaults] = await Promise.all(
			[
				getTeacherAssignment(localStorage.token, assignmentId),
				getTeacherClassrooms(localStorage.token),
				getTeacherReflectionQuestionSets(localStorage.token).catch((error) => {
					console.error(error);
					return [];
				}),
				getTeacherAssignmentDefaults(localStorage.token)
			]
		);
		allowedTaskModes = assignmentDefaults.allowed_task_modes;
		teachingConfigs = assignmentDefaults.teaching_configs;
		photoTranscriptionModel = assignmentDefaults.photo_transcription_model;
		imageParsingModel = assignmentDefaults.image_parsing_model;
		thinkingPolicy = assignmentDefaults.thinking;
		classrooms = teacherClassrooms;
		reflectionQuestionSets = questionSets;
		item = assignmentItem;
		syncDraft();
	};

	const save = async () => {
		if (!classroomId) {
			toast.error(t('Classroom is required.'));
			return;
		}
		const { payload, error } = buildAssignmentPayload(draft, t, thinkingPolicy?.control);
		if (error) {
			toast.error(error);
			return;
		}
		// The picker displays minutes. Editing another field must not round away
		// seconds from an existing deadline created through the API.
		if (draft.dueAt === toLocalDateTimeInput(item.assignment.due_at)) {
			payload.due_at = item.assignment.due_at;
		}
		pendingPayload = {
			...payload,
			expected_config_revision: item.assignment.config_revision,
			change_summary: '',
			adopt_latest_teaching_config: adoptLatest,
			classroom_id: classroomId
		};
		const labels = {
			title: 'Assignment title',
			description: 'Assignment description',
			due_at: 'Due At',
			score_max: 'Maximum Score',
			scoring_mode: 'Scoring',
			rubric_schema: 'Rubric',
			reflection_questions: 'Reflection Before Submitting',
			task_mode: 'Assignment type',
			coaching_style: 'AI Coaching Style',
			photo_transcription_enabled: '照片转正文',
			image_reading_enabled: 'AI 读取参考图片',
			challenge_enabled: 'AI Reader Check Before Submitting',
			challenge_rounds: 'Rounds',
			challenge_focus_keys: 'Rubric',
			model_params: 'AI Coaching',
			classroom_id: 'Classroom'
		};
		const describe = (key: string, value: any) => {
			if (value == null || value === '') return t('无');
			if (key === 'due_at') return new Date(value * 1000).toLocaleString();
			if (key === 'task_mode') return t(taskTypeLabel(value));
			if (key === 'coaching_style')
				return t({ socratic: 'Socratic', balanced: 'Balanced', hands_off: 'Hands-off' }[value]);
			if (key === 'classroom_id')
				return classrooms.find((item) => item.classroom.id === value)?.classroom.name ?? value;
			if (key === 'scoring_mode') return t(value === 'total' ? '仅总分与总评' : '按维度评分');
			if (key === 'rubric_schema')
				return value.criteria.map((c) => `${c.label} · ${c.max_score}`).join('\n') || t('无');
			if (key === 'reflection_questions')
				return (
					value
						.map(
							(q) =>
								`${q.prompt} (${t(q.required ? 'Required' : 'Optional')})${q.options.length ? '\n' + q.options.join(' / ') : ''}`
						)
						.join('\n\n') || t('无')
				);
			if (typeof value === 'boolean') return t(value ? 'On' : 'Off');
			if (key === 'challenge_focus_keys')
				return value
					.map((id) => draft.rubricCriteria.find((c) => c.key === id)?.label ?? id)
					.join(' / ');
			if (key === 'model_params')
				return `${t(THINKING_SETTING_TEXT[value.thinking ?? 'model_default'])} · ${t(value.students_choose_thinking ? 'Students may turn thinking off' : 'Admin only')}`;
			return String(value);
		};
		changePreview = Object.keys(labels)
			.filter(
				(key) =>
					key in pendingPayload &&
					JSON.stringify(pendingPayload[key] ?? '') !== JSON.stringify(item.assignment[key] ?? '')
			)
			.map((key) => ({
				label: t(labels[key]),
				before: describe(key, item.assignment[key]),
				after: describe(key, pendingPayload[key])
			}));
		if (
			adoptLatest &&
			item.assignment.teaching_config.version !== teachingConfigs[draft.taskMode]?.version
		)
			changePreview.push({
				label: t('AI 辅导说明'),
				before: `v${item.assignment.teaching_config.version}`,
				after: `v${teachingConfigs[draft.taskMode]?.version}`
			});
		if (!changePreview.length) {
			toast.info(t('没有需要保存的修改。'));
			return;
		}
		saveError = '';
		showSaveConfirm = true;
	};

	const confirmSave = async () => {
		if (!pendingPayload || saving || !changeSummary.trim()) return;
		saving = true;
		saveError = '';
		try {
			await updateAssignment(localStorage.token, assignmentId, {
				...pendingPayload,
				change_summary: changeSummary.trim()
			});
			showSaveConfirm = false;
			changeSummary = '';
			adoptLatest = false;
			await loadData();
			aiSummaryVersion += 1;
			toast.success(t('Assignment updated.'));
		} catch (error) {
			saveError = resolveErrorMessage(error, t);
			toast.error(saveError);
		} finally {
			saving = false;
		}
	};

	const remove = async () => {
		try {
			await deleteAssignment(localStorage.token, assignmentId);
			toast.success(t('Assignment deleted.'));
			goto('/teacher/assignments');
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		}
	};

	onMount(async () => {
		try {
			await loadData();
		} catch (error) {
			loadError = resolveErrorMessage(error, t);
			toast.error(loadError);
		} finally {
			loading = false;
		}
	});
</script>

<TeacherPageShell
	crumbs={[{ label: $i18n.t('Assignments'), href: '/teacher/assignments' }]}
	title={item?.assignment?.title ?? ''}
	tabs={assignmentTabs(assignmentId)}
>
	<div class="mx-auto max-w-6xl px-4 py-6">
		{#if loading}
			<EduStateCard>{$i18n.t('Loading assignment...')}</EduStateCard>
		{:else if loadError}
			<EduStateCard tone="error">{loadError}</EduStateCard>
		{:else if draft}
			{#if draft.taskMode !== 'revise_argument'}{#key aiSummaryVersion}
					<AssignmentAiSummary {assignmentId} />
				{/key}{/if}
			<div class="mb-4 grid gap-2 text-sm">
				<p class="rounded-xl bg-sky-50 p-3 text-sky-800 dark:bg-sky-950/40 dark:text-sky-200">
					{$i18n.t('修改作业设置需填写修改说明；隐藏和恢复显示除外。')}
				</p>
				{#if item.assignment.change_summary}
					<p class="text-gray-500 whitespace-pre-wrap break-words">
						{$i18n.t('最近修改说明')}：{item.assignment.change_summary}
					</p>
				{/if}
				{#if !item.task_mode_locked && draft.taskMode !== 'revise_argument'}<label
						><input type="checkbox" bind:checked={adoptLatest} />
						{$i18n.t('采用该类型最新教学配置')}</label
					>{/if}
			</div>
			<AssignmentForm
				{photoTranscriptionModel}
				{imageParsingModel}
				{allowedTaskModes}
				{teachingConfigs}
				teachingSnapshot={item.assignment.teaching_config}
				bind:draft
				bind:classroomId
				{classrooms}
				{hasSubmissions}
				taskModeLocked={item?.task_mode_locked ?? false}
				{reflectionQuestionSets}
				currentAssignmentId={assignmentId}
				{thinkingPolicy}
			>
				<svelte:fragment slot="footer">
					<div
						class="sticky bottom-0 z-10 flex justify-end border-t border-gray-100 bg-white/90 py-3 backdrop-blur dark:border-gray-850 dark:bg-gray-900/90"
					>
						<EduButton variant="primary" disabled={saving} on:click={save}>
							{saving ? $i18n.t('Saving...') : $i18n.t('Save Changes')}
						</EduButton>
					</div>

					{#if draft.taskMode === 'revise_argument'}<TeachingPreparationPanel
							bind:draft
							assignment={item.assignment}
							template={teachingConfigs.revise_argument}
						/>{/if}
					<EduCard>
						<div class="flex flex-wrap items-center justify-between gap-3">
							<div>
								<h2 class="text-base font-semibold">
									{$i18n.t(item.assignment.hidden ? 'Hidden Assignment' : 'Assignment Visibility')}
								</h2>
								<p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
									{$i18n.t(
										'Hidden assignments are unavailable to students. Writing and submissions are preserved, and you can show the assignment again.'
									)}
								</p>
							</div>
							<EduButton disabled={changingVisibility} on:click={toggleVisibility}
								>{$i18n.t(
									item.assignment.hidden ? 'Show Assignment' : 'Hide Assignment'
								)}</EduButton
							>
						</div>
					</EduCard>
					<EduCard class="border-red-200 dark:border-red-900/60">
						<h2 class="text-base font-semibold text-red-700 dark:text-red-400">
							{$i18n.t('Danger Zone')}
						</h2>
						<div class="mt-4 flex flex-wrap items-center justify-between gap-3">
							<div>
								<div class="text-sm font-medium">{$i18n.t('Delete Assignment')}</div>
								<div class="text-xs text-gray-500 dark:text-gray-400">
									{$i18n.t('Only assignments without any student activity can be deleted.')}
								</div>
							</div>
							<EduButton variant="danger" on:click={() => (showDeleteConfirm = true)}>
								{$i18n.t('Delete')}
							</EduButton>
						</div>
					</EduCard>
				</svelte:fragment>
			</AssignmentForm>
		{/if}
	</div>

	<Modal size="lg" bind:show={showSaveConfirm} title={$i18n.t('请核对本次修改')} busy={saving}>
		<p class="my-2 text-sm">
			{$i18n.t('已开始但尚未提交')}：{item?.writing_count ?? 0}；{$i18n.t(
				'已提交'
			)}：{item?.submission_count ?? 0}
		</p>
		<p class="mb-3 text-xs text-gray-500">
			{$i18n.t('新要求作用于之后的辅导与提交，历史记录保留原内容。')}
		</p>
		{#if pendingPayload?.due_at && pendingPayload.due_at < Date.now() / 1000}<p
				class="mb-3 text-sm text-amber-700"
			>
				{$i18n.t('新的截止时间将立即停止尚未获得延期的学生写作。')}
			</p>{/if}
		{#each changePreview as change}
			<section class="mb-4 rounded-xl border p-3 dark:border-gray-700">
				<h3 class="mb-2 text-sm font-medium">{change.label}</h3>
				<div class="grid gap-3 text-sm sm:grid-cols-2">
					<div>
						<div class="text-xs text-gray-500">{$i18n.t('修改前')}</div>
						<p class="whitespace-pre-wrap break-words">{change.before}</p>
					</div>
					<div>
						<div class="text-xs text-gray-500">{$i18n.t('修改后')}</div>
						<p class="whitespace-pre-wrap break-words">{change.after}</p>
					</div>
				</div>
			</section>
		{/each}
		<AssignmentChangeReason
			id="assignment-change-reason"
			bind:value={changeSummary}
			disabled={saving}
		/>
		{#if saveError}<p role="alert" class="mt-3 text-sm text-red-600">{saveError}</p>{/if}
		<svelte:fragment slot="footer">
			<EduButton disabled={saving} on:click={() => (showSaveConfirm = false)}
				>{$i18n.t('Cancel')}</EduButton
			><EduButton
				variant="primary"
				disabled={saving || !changeSummary.trim()}
				on:click={confirmSave}>{$i18n.t('确认保存')}</EduButton
			>
		</svelte:fragment>
	</Modal>

	<ConfirmDialog
		confirmLabel={$i18n.t('Delete')}
		variant="danger"
		bind:show={showDeleteConfirm}
		title={$i18n.t('Delete Assignment')}
		message={$i18n.t(
			'Only assignments without any student activity can be deleted. This cannot be undone. Continue?'
		)}
		on:confirm={remove}
	/>
</TeacherPageShell>
