<script lang="ts">
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	let confirmation: ConfirmDialog;
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext } from 'svelte';
	import { get } from 'svelte/store';

	import { config } from '$lib/stores';
	import { TASK_TYPES, isRevision } from '$lib/utils/task-types';
	import { applyTeachingDefaults } from '$lib/utils/assignment-form';
	import type { TeachingConfig } from '$lib/apis/education';

	import type {
		ReflectionQuestionSet,
		TaskMode,
		ThinkingControl,
		ThinkingSetting
	} from '$lib/apis/education';
	import {
		getDefaultRubricCriteria,
		isSameRubric,
		rubricTotal,
		type AssignmentDraft,
		type DefaultRubrics
	} from '$lib/utils/assignment-form';
	import { getClassroomDisplayName } from '$lib/utils/education';
	import { adaptDefaultReflectionQuestions } from '$lib/utils/reflection-questions';
	import EduCard from './EduCard.svelte';
	import EduDateTimeField from './EduDateTimeField.svelte';
	import RubricCriteriaEditor from './RubricCriteriaEditor.svelte';
	import CoachingStyleSelector from './CoachingStyleSelector.svelte';
	import ChallengeSettings from './ChallengeSettings.svelte';
	import AssignmentThinkingSettings from './AssignmentThinkingSettings.svelte';
	import AssignmentImageReadingSettings from './AssignmentImageReadingSettings.svelte';
	import { THINKING_SETTING_TEXT } from '$lib/utils/ai-steps';
	import ReflectionQuestionsEditor from './ReflectionQuestionsEditor.svelte';
	import { EDU_FIELD_CLASS, eduSegmentClass } from './styles';
	import DisclosureChevron from '$lib/components/common/DisclosureChevron.svelte';
	import { disclosure } from '$lib/utils/disclosure';

	// 新建作业与作业设置共用。此前是一张九段平铺的长表单,满分和评分维度隔着好几块;
	// 现在分四组,满分与维度放一起(二者要加总一致),辅导与反思默认展开。

	export let draft: AssignmentDraft;
	export let photoTranscriptionModel: import('$lib/apis/education').ImageParsingModelView | null =
		null;
	export let imageParsingModel: import('$lib/apis/education').ImageParsingModelView | null = null;
	export let allowedTaskModes: TaskMode[] = [];
	export let teachingConfigs: Partial<Record<TaskMode, TeachingConfig>> = {};
	export let teachingSnapshot: TeachingConfig | null = null;
	$: shownTeaching =
		teachingSnapshot?.task_mode === draft.taskMode
			? teachingSnapshot
			: teachingConfigs[draft.taskMode];
	export let classrooms: Array<{ classroom: { id: string; name: string } }> = [];
	/** 新建:可多选班级,一次发到多个班。编辑:单选。 */
	export let multiClassroom = false;
	export let selectedClassroomIds: Set<string> = new Set();
	export let classroomId = '';
	/** 已有提交后班级锁定；评分设置仍可编辑。 */
	export let hasSubmissions = false;
	export let reflectionQuestionSets: ReflectionQuestionSet[] = [];
	export let reflectionNotice = '';
	export let currentAssignmentId = '';
	/** 有学生交了初稿或已有提交后,作业形式锁定(后端同样拒绝)。 */
	export let taskModeLocked = false;
	/** 只有新建作业传:管理员按作业形式设的默认评分维度。作业设置页不传,改形式不碰已有维度。 */
	/** 管理员对辅导对话思考档位的下放方式与默认;仅管理员时表单不显示思考设置。 */
	export let thinkingPolicy: { control: ThinkingControl; default: ThinkingSetting } | null = null;

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	// 管理员可以关掉辅导风格(怎么辅导全写在任务说明里),这时表单不出现档位。
	$: coachingEnabled =
		!isRevision(draft.taskMode) && ($config?.features?.enable_education_coaching_styles ?? true);
	// 修订初稿作业没有试读，第 3 节标题里就不提「试读」;档位关了、思考也没下放时这一节没东西可设，整节不出现。
	$: thinkingDelegated =
		draft.taskMode !== 'revise_argument' && !!thinkingPolicy && thinkingPolicy.control !== 'admin';
	// Every assignment offers the teacher-controlled image-reading switch.
	const hasCoachingSettings = true;
	$: hasReaderCheck = !isRevision(draft.taskMode) && draft.scoringMode === 'dimensions';
	$: aiSectionLabel =
		hasCoachingSettings && hasReaderCheck
			? 'AI Coaching & Reader Check'
			: hasCoachingSettings
				? 'AI Coaching'
				: 'AI Reader Check';
	$: showAiSection = hasCoachingSettings || hasReaderCheck;
	$: SECTIONS = [
		{ id: 'assignment-basics', label: 'Basics' },
		{ id: 'assignment-scoring', label: 'Scoring' },
		...(showAiSection ? [{ id: 'assignment-ai', label: aiSectionLabel }] : []),
		{ id: 'assignment-reflection', label: 'Reflection Before Submitting' },
		...(draft.taskMode === 'revise_argument'
			? [{ id: 'assignment-teaching', label: 'AI 辅导设置' }]
			: [])
	];
	const COACHING_TITLES = { socratic: 'Socratic', balanced: 'Balanced', hands_off: 'Hands-off' };
	// 两种形式的差别在于作业开始时初稿是否已经存在。修订初稿作业没有提交前试读:
	// 左侧对话本身就是按维度诊断与追问,提交前再质疑一次是重复。
	const TASK_MODES = TASK_TYPES;

	let aiOpen = true;
	// 反思题折起来只剩一行摘要,老师以为题没了;它是提交那一刻学生要答的,默认展开。
	let reflectionOpen = true;

	$: if (draft.scoringMode === 'dimensions') draft.scoreMax = rubricTotal(draft.rubricCriteria);
	$: isReviseDraft = isRevision(draft.taskMode);
	$: taskModeHint = TASK_MODES.find((mode) => mode.key === draft.taskMode)?.hint ?? '';
	$: aiSummary = [
		t(draft.photoTranscriptionEnabled ? '照片转正文已开启' : '照片转正文已关闭'),
		t(draft.imageReadingEnabled ? '参考图片识读已开启' : '参考图片识读已关闭'),
		...(coachingEnabled ? [t(COACHING_TITLES[draft.coachingStyle])] : []),
		...(thinkingDelegated && draft.thinking
			? [t('Thinking: {{level}}', { level: t(THINKING_SETTING_TEXT[draft.thinking]) })]
			: []),
		...(isReviseDraft
			? []
			: [
					draft.challengeEnabled
						? t('AI reader check on · {{count}} rounds', { count: draft.challengeRounds })
						: t('AI reader check off')
				])
	].join(' · ');
	$: reflectionSummary = isReviseDraft
		? t('{{count}} reflection questions', {
				count: draft.reflectionQuestions.length
			})
		: t('{{count}} reflection questions, plus "Did you use AI?"', {
				count: draft.reflectionQuestions.length
			});

	// 两种形式的默认反思题不同（修订初稿不问和修改清单重复的题）。
	// 题目还是原形式的默认题、教师没动过时，跟着换；动过就不碰。
	// 评分维度同理：还是原形式的默认维度、满分也没改时，换成新形式的默认（修订初稿的
	// 第一次通读按评分维度逐项下结论，实例会把这一份设成提示词里的标准）。
	const chooseTaskMode = async (taskMode: TaskMode) => {
		if (taskMode === draft.taskMode || !allowedTaskModes.includes(taskMode)) return;
		const next = teachingConfigs[taskMode];
		if (!next) return;
		if (
			!(await confirmation.ask({
				title: t('切换作业类型'),
				message: t('切换类型会采用目标类型的教学规则、默认说明、评分与反思，请确认替换这些字段。'),
				confirmLabel: t('确认切换')
			}))
		)
			return;
		draft = applyTeachingDefaults(draft, next);
		teachingSnapshot = null;
	};

	const toggleClassroom = (id: string) => {
		const next = new Set(selectedClassroomIds);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		selectedClassroomIds = next;
	};
</script>

<div class="min-w-0 lg:grid lg:grid-cols-[11rem_minmax(0,1fr)] lg:gap-8">
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

	<div class="grid min-w-0 grid-cols-1 gap-5">
		<EduCard padding="lg">
			<section id="assignment-basics" class="grid min-w-0 grid-cols-1 scroll-mt-4 gap-4">
				<h2 class="text-base font-semibold">1 · {$i18n.t('Basics')}</h2>
				<div>
					<div class="mb-2 text-sm font-medium">{$i18n.t('Assignment type')}</div>
					<div class="flex flex-wrap gap-2">
						{#each TASK_MODES.filter((mode) => allowedTaskModes.includes(mode.key) || (currentAssignmentId && mode.key === draft.taskMode)) as mode}
							<button
								type="button"
								class={eduSegmentClass(draft.taskMode === mode.key)}
								aria-pressed={draft.taskMode === mode.key}
								disabled={taskModeLocked || !allowedTaskModes.includes(mode.key)}
								on:click={() => chooseTaskMode(mode.key)}
							>
								{$i18n.t(mode.title)}
							</button>
						{/each}
					</div>
					<div class="mt-2 text-xs text-gray-400">{$i18n.t(taskModeHint)}</div>
					{#if allowedTaskModes.length < TASK_MODES.length && !taskModeLocked}
						<p class="mt-2 text-xs text-gray-500">
							{$i18n.t('可布置的作业类型由管理员设置。如需其他类型，请联系管理员。')}
						</p>
					{/if}
					{#if taskModeLocked}
						<div class="mt-1 text-xs text-gray-400">
							{$i18n.t('The assignment type is locked once a student has started.')}
						</div>
					{/if}
				</div>
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
					<p class="mt-1 text-xs text-gray-500">
						{$i18n.t('填写本次题目、材料范围及完成要求；具体辅导方式见 AI 辅导设置或说明。')}
					</p>
				</div>
				<div class="md:max-w-sm">
					<div class="mb-2 text-sm font-medium">{$i18n.t('Due At')}</div>
					<EduDateTimeField
						bind:value={draft.dueAt}
						required
						className="w-full {EDU_FIELD_CLASS}"
					/>
				</div>
			</section>
		</EduCard>

		{#if shownTeaching && draft.taskMode !== 'revise_argument'}
			<EduCard padding="lg">
				<h2 class="font-semibold">{$i18n.t('AI 辅导说明')} · v{shownTeaching.version}</h2>
				<p class="mt-2 text-sm text-gray-500">
					{$i18n.t('学生可按需讨论、修改与复看，并自主结束提交，无需 AI 认可。')}
				</p>
				<details class="mt-2 text-sm">
					<summary>{$i18n.t('查看辅导方式')}</summary>
					<p class="whitespace-pre-wrap">{shownTeaching.prompt}</p>
				</details>
			</EduCard>
		{/if}

		<EduCard padding="lg">
			<section id="assignment-scoring" class="grid min-w-0 grid-cols-1 scroll-mt-4 gap-4">
				<h2 class="text-base font-semibold">2 · {$i18n.t('Scoring')}</h2>
				<p class="text-sm text-gray-500">
					{$i18n.t('评分设置用于教师评阅，AI 按本作业类型的教学规则辅导。')}
				</p>
				{#if hasSubmissions}
					<p class="text-sm text-gray-500">
						{$i18n.t('新评分设置适用于尚未批改的提交；已发布成绩保留原评分标准。')}
					</p>
				{/if}
				<select bind:value={draft.scoringMode} class={EDU_FIELD_CLASS}>
					<option value="dimensions">{$i18n.t('按维度评分')}</option>
					<option value="total">{$i18n.t('仅总分与总评')}</option>
				</select>
				<div class="md:max-w-xs">
					<div class="mb-2 text-sm font-medium">{$i18n.t('Maximum Score')}</div>
					<input
						bind:value={draft.scoreMax}
						type="number"
						min="1"
						step="1"
						required
						class="w-full {EDU_FIELD_CLASS}"
					/>
				</div>
				{#if draft.scoringMode === 'dimensions'}
					<RubricCriteriaEditor
						bind:criteria={draft.rubricCriteria}
						scoreMax={draft.scoreMax}
					/>
				{/if}
			</section>
		</EduCard>

		{#if showAiSection}
			<EduCard padding="lg">
				<section id="assignment-ai" class="scroll-mt-4">
					<button
						type="button"
						class="flex w-full items-start justify-between gap-4 text-left"
						aria-expanded={aiOpen}
						aria-controls="assignment-ai-content"
						on:click={() => (aiOpen = !aiOpen)}
					>
						<div>
							<h2 class="text-base font-semibold">3 · {$i18n.t(aiSectionLabel)}</h2>
							{#if !aiOpen}
								<div class="mt-1 text-sm text-gray-500 dark:text-gray-400">{aiSummary}</div>
							{/if}
						</div>
						<span class="flex shrink-0 items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
							{aiOpen ? $i18n.t('Collapse') : $i18n.t('Expand')}
							<DisclosureChevron open={aiOpen} />
						</span>
					</button>
					<div id="assignment-ai-content" use:disclosure={aiOpen}>
						<div class="pt-4 grid gap-4">
							<AssignmentImageReadingSettings
								bind:enabled={draft.imageReadingEnabled}
								bind:photoEnabled={draft.photoTranscriptionEnabled}
								{photoTranscriptionModel}
								platformModel={imageParsingModel}
							/>
							{#if coachingEnabled}
								<CoachingStyleSelector bind:value={draft.coachingStyle} />
							{/if}
							{#if thinkingDelegated && thinkingPolicy}
								<AssignmentThinkingSettings
									control={thinkingPolicy.control}
									adminDefault={thinkingPolicy.default}
									bind:value={draft.thinking}
									bind:studentsChoose={draft.studentsChooseThinking}
								/>
							{/if}
							{#if hasReaderCheck}
								<ChallengeSettings
									criteria={draft.rubricCriteria}
									bind:enabled={draft.challengeEnabled}
									bind:rounds={draft.challengeRounds}
									bind:focusKeys={draft.challengeFocusKeys}
								/>
							{/if}
						</div>
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
					aria-controls="assignment-reflection-content"
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
					<span class="flex shrink-0 items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
						{reflectionOpen ? $i18n.t('Collapse') : $i18n.t('Expand')}
						<DisclosureChevron open={reflectionOpen} />
					</span>
				</button>
				<div id="assignment-reflection-content" use:disclosure={reflectionOpen}>
					<div class="pt-4">
						<ReflectionQuestionsEditor
							bind:questions={draft.reflectionQuestions}
							questionSets={reflectionQuestionSets}
							notice={reflectionNotice}
							taskMode={draft.taskMode}
							defaultQuestions={teachingConfigs[draft.taskMode]?.reflection_questions ?? null}
							{currentAssignmentId}
							{hasSubmissions}
						/>
					</div>
				</div>
			</section>
		</EduCard>

		<slot name="footer" />
	</div>
</div>

<ConfirmDialog bind:this={confirmation} />
