<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext } from 'svelte';
	import { get } from 'svelte/store';

	import { config } from '$lib/stores';

	import type { ReflectionQuestionSet, TaskMode } from '$lib/apis/education';
	import type { AssignmentDraft } from '$lib/utils/assignment-form';
	import { getClassroomDisplayName } from '$lib/utils/education';
	import { adaptDefaultReflectionQuestions } from '$lib/utils/reflection-questions';
	import EduCard from './EduCard.svelte';
	import EduDateTimeField from './EduDateTimeField.svelte';
	import RubricCriteriaEditor from './RubricCriteriaEditor.svelte';
	import CoachingStyleSelector from './CoachingStyleSelector.svelte';
	import ChallengeSettings from './ChallengeSettings.svelte';
	import ReflectionQuestionsEditor from './ReflectionQuestionsEditor.svelte';
	import { EDU_FIELD_CLASS, eduSegmentClass } from './styles';

	// 新建作业与作业设置共用。此前是一张九段平铺的长表单,满分和评分维度隔着好几块;
	// 现在分四组,满分与维度放一起(二者要加总一致),辅导/试读和反思题这两组
	// 大多沿用上次的配置,默认折叠成一行摘要。

	export let draft: AssignmentDraft;
	export let classrooms: Array<{ classroom: { id: string; name: string } }> = [];
	/** 新建:可多选班级,一次发到多个班。编辑:单选。 */
	export let multiClassroom = false;
	export let selectedClassroomIds: Set<string> = new Set();
	export let classroomId = '';
	/** 已有提交后,班级、满分与评分维度锁定(后端同样拒绝)。 */
	export let hasSubmissions = false;
	export let reflectionQuestionSets: ReflectionQuestionSet[] = [];
	export let reflectionNotice = '';
	export let currentAssignmentId = '';
	export let expandAll = false;
	/** 有学生交了初稿或已有提交后,作业形式锁定(后端同样拒绝)。 */
	export let taskModeLocked = false;

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	// 管理员可以关掉辅导风格(怎么辅导全写在任务说明里),这时表单不出现档位。
	$: coachingEnabled = $config?.features?.enable_education_coaching_styles ?? true;
	// 修订初稿作业没有试读，第 3 节标题里就不提「试读」;档位也关了时这一节没东西可设，整节不出现。
	$: aiSectionLabel = !coachingEnabled
		? 'AI Reader Check'
		: draft.taskMode === 'revise_draft'
			? 'AI Coaching'
			: 'AI Coaching & Reader Check';
	$: showAiSection = coachingEnabled || draft.taskMode !== 'revise_draft';
	$: SECTIONS = [
		{ id: 'assignment-basics', label: 'Basics' },
		{ id: 'assignment-scoring', label: 'Scoring' },
		...(showAiSection ? [{ id: 'assignment-ai', label: aiSectionLabel }] : []),
		{ id: 'assignment-reflection', label: 'Reflection Before Submitting' }
	];
	const COACHING_TITLES = { socratic: 'Socratic', balanced: 'Balanced', hands_off: 'Hands-off' };
	// 两种形式的差别在于作业开始时初稿是否已经存在。修订初稿作业没有提交前试读:
	// 左侧对话本身就是按维度诊断与追问,提交前再质疑一次是重复。
	const TASK_MODES = [
		{
			key: 'from_scratch',
			title: 'Write from scratch',
			hint: 'Students start from a blank page and write with the AI coach.'
		},
		{
			key: 'revise_draft',
			title: 'Revise a draft',
			hint: 'Students first paste or upload the draft they wrote outside class; it is frozen as the starting point, and the AI chat unlocks only after that. There is no pre-submission reader check.'
		}
	] as const;

	let aiOpen = expandAll;
	let reflectionOpen = expandAll;

	$: isReviseDraft = draft.taskMode === 'revise_draft';
	$: taskModeHint = TASK_MODES.find((mode) => mode.key === draft.taskMode)?.hint ?? '';
	$: aiSummary = [
		...(coachingEnabled ? [t(COACHING_TITLES[draft.coachingStyle])] : []),
		...(isReviseDraft
			? []
			: [
					draft.challengeEnabled
						? t('AI reader check on · {{count}} rounds', { count: draft.challengeRounds })
						: t('AI reader check off')
				])
	].join(' · ');
	$: reflectionSummary = isReviseDraft
		? t('{{count}} reflection questions, plus the revision list', {
				count: draft.reflectionQuestions.length
			})
		: t('{{count}} reflection questions, plus "Did you use AI?"', {
				count: draft.reflectionQuestions.length
			});

	// 两种形式的默认反思题不同（修订初稿不问和修改清单重复的题）。
	// 题目还是原形式的默认题、教师没动过时，跟着换；动过就不碰。
	const chooseTaskMode = (taskMode: TaskMode) => {
		draft.taskMode = taskMode;
		draft.reflectionQuestions = adaptDefaultReflectionQuestions(
			draft.reflectionQuestions,
			t,
			taskMode
		);
	};

	const toggleClassroom = (id: string) => {
		const next = new Set(selectedClassroomIds);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		selectedClassroomIds = next;
	};
</script>

<div class="lg:grid lg:grid-cols-[11rem_1fr] lg:gap-8">
	<nav class="hidden lg:block" aria-label={$i18n.t('Sections')}>
		<ol class="sticky top-4 space-y-1 text-sm">
			{#each SECTIONS as section, index}
				<li>
					<a
						href={`#${section.id}`}
						class="flex gap-2 rounded-lg px-2 py-1.5 text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-850 dark:hover:text-gray-100"
						on:click={() => {
							if (section.id === 'assignment-ai') aiOpen = true;
							if (section.id === 'assignment-reflection') reflectionOpen = true;
						}}
					>
						<span class="tabular-nums text-gray-400">{index + 1}</span>
						<span>{$i18n.t(section.label)}</span>
					</a>
				</li>
			{/each}
		</ol>
	</nav>

	<div class="grid gap-5">
		<EduCard padding="lg">
			<section id="assignment-basics" class="grid scroll-mt-4 gap-4">
				<h2 class="text-base font-semibold">1 · {$i18n.t('Basics')}</h2>
				<div>
					<div class="mb-2 flex items-center justify-between">
						<div class="text-sm font-medium">{$i18n.t('Classroom')}</div>
						{#if multiClassroom}
							<div class="text-xs text-gray-400">
								{$i18n.t('{{count}} selected', { count: selectedClassroomIds.size })}
							</div>
						{/if}
					</div>
					{#if multiClassroom}
						<div class="flex flex-wrap gap-2">
							{#each classrooms as item}
								<button
									type="button"
									class={eduSegmentClass(selectedClassroomIds.has(item.classroom.id))}
									aria-pressed={selectedClassroomIds.has(item.classroom.id)}
									on:click={() => toggleClassroom(item.classroom.id)}
								>
									{getClassroomDisplayName(item.classroom.name, t)}
								</button>
							{/each}
						</div>
						<div class="mt-2 text-xs text-gray-400">
							{$i18n.t('Select one or more classrooms; the assignment is published to each.')}
						</div>
					{:else}
						<select
							bind:value={classroomId}
							disabled={hasSubmissions}
							class="w-full {EDU_FIELD_CLASS} disabled:opacity-60"
						>
							{#each classrooms as item}
								<option value={item.classroom.id}>
									{getClassroomDisplayName(item.classroom.name, t)}
								</option>
							{/each}
						</select>
						{#if hasSubmissions}
							<div class="mt-1 text-xs text-gray-400">
								{$i18n.t('The classroom is locked after the first submission.')}
							</div>
						{/if}
					{/if}
				</div>
				<div>
					<div class="mb-2 text-sm font-medium">{$i18n.t('Assignment title')}</div>
					<input
						bind:value={draft.title}
						class="w-full {EDU_FIELD_CLASS}"
						placeholder={$i18n.t('Academic Argument 1')}
					/>
				</div>
				<div>
					<div class="mb-2 text-sm font-medium">{$i18n.t('Assignment description')}</div>
					<textarea
						bind:value={draft.description}
						class="min-h-32 w-full {EDU_FIELD_CLASS}"
						placeholder={$i18n.t('Write a short academic argument.')}
					></textarea>
				</div>
				<div class="md:max-w-sm">
					<div class="mb-2 text-sm font-medium">{$i18n.t('Due At')}</div>
					<EduDateTimeField bind:value={draft.dueAt} required className="w-full {EDU_FIELD_CLASS}" />
				</div>
				<div>
					<div class="mb-2 text-sm font-medium">{$i18n.t('Assignment type')}</div>
					<div class="flex flex-wrap gap-2">
						{#each TASK_MODES as mode}
							<button
								type="button"
								class={eduSegmentClass(draft.taskMode === mode.key)}
								aria-pressed={draft.taskMode === mode.key}
								disabled={taskModeLocked}
								on:click={() => chooseTaskMode(mode.key)}
							>
								{$i18n.t(mode.title)}
							</button>
						{/each}
					</div>
					<div class="mt-2 text-xs text-gray-400">{$i18n.t(taskModeHint)}</div>
					{#if taskModeLocked}
						<div class="mt-1 text-xs text-gray-400">
							{$i18n.t('The assignment type is locked once a student has started.')}
						</div>
					{/if}
				</div>
			</section>
		</EduCard>

		<EduCard padding="lg">
			<section id="assignment-scoring" class="grid scroll-mt-4 gap-4">
				<h2 class="text-base font-semibold">2 · {$i18n.t('Scoring')}</h2>
				<div class="md:max-w-xs">
					<div class="mb-2 text-sm font-medium">{$i18n.t('Maximum Score')}</div>
					<input
						bind:value={draft.scoreMax}
						type="number"
						min="1"
						step="1"
						required
						disabled={hasSubmissions}
						class="w-full {EDU_FIELD_CLASS} disabled:opacity-60"
					/>
					{#if hasSubmissions}
						<div class="mt-1 text-xs text-gray-400">
							{$i18n.t('Maximum score is locked after the first submission.')}
						</div>
					{/if}
				</div>
				<RubricCriteriaEditor
					bind:criteria={draft.rubricCriteria}
					scoreMax={draft.scoreMax}
					disabled={hasSubmissions}
					lockedHint={hasSubmissions
						? $i18n.t('Rubric criteria are locked after the first submission.')
						: ''}
				/>
			</section>
		</EduCard>

		{#if showAiSection}
			<EduCard padding="lg">
				<section id="assignment-ai" class="scroll-mt-4">
					<button
						type="button"
						class="flex w-full items-start justify-between gap-4 text-left"
						aria-expanded={aiOpen}
						on:click={() => (aiOpen = !aiOpen)}
					>
						<div>
							<h2 class="text-base font-semibold">3 · {$i18n.t(aiSectionLabel)}</h2>
							{#if !aiOpen}
								<div class="mt-1 text-sm text-gray-500 dark:text-gray-400">{aiSummary}</div>
							{/if}
						</div>
						<span class="shrink-0 text-sm text-gray-500 dark:text-gray-400">
							{aiOpen ? $i18n.t('Collapse') : $i18n.t('Edit')}
						</span>
					</button>
					<div class="mt-4 grid gap-4" class:hidden={!aiOpen}>
						{#if coachingEnabled}
							<CoachingStyleSelector bind:value={draft.coachingStyle} />
						{/if}
						{#if !isReviseDraft}
							<ChallengeSettings
								criteria={draft.rubricCriteria}
								bind:enabled={draft.challengeEnabled}
								bind:rounds={draft.challengeRounds}
								bind:focusKeys={draft.challengeFocusKeys}
							/>
						{/if}
					</div>
				</section>
			</EduCard>
		{/if}

		<EduCard padding="lg">
			<section id="assignment-reflection" class="scroll-mt-4">
				<button
					type="button"
					class="flex w-full items-start justify-between gap-4 text-left"
					aria-expanded={reflectionOpen}
					on:click={() => (reflectionOpen = !reflectionOpen)}
				>
					<div>
						<h2 class="text-base font-semibold">
							{showAiSection ? 4 : 3} · {$i18n.t('Reflection Before Submitting')}
						</h2>
						{#if !reflectionOpen}
							<div class="mt-1 text-sm text-gray-500 dark:text-gray-400">{reflectionSummary}</div>
							{#if reflectionNotice}
								<div class="mt-1 text-xs text-gray-400">{reflectionNotice}</div>
							{/if}
						{/if}
					</div>
					<span class="shrink-0 text-sm text-gray-500 dark:text-gray-400">
						{reflectionOpen ? $i18n.t('Collapse') : $i18n.t('Edit')}
					</span>
				</button>
				<div class="mt-4" class:hidden={!reflectionOpen}>
					<ReflectionQuestionsEditor
						bind:questions={draft.reflectionQuestions}
						questionSets={reflectionQuestionSets}
						notice={reflectionNotice}
						taskMode={draft.taskMode}
						{currentAssignmentId}
						{hasSubmissions}
					/>
				</div>
			</section>
		</EduCard>

		<slot name="footer" />
	</div>
</div>
