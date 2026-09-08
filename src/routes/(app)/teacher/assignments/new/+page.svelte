<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { createAssignment, getTeacherAssignment, getTeacherClassrooms } from '$lib/apis/education';
	import type { CoachingStyle } from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import EduDateTimeField from '$lib/components/education/EduDateTimeField.svelte';
	import RubricCriteriaEditor from '$lib/components/education/RubricCriteriaEditor.svelte';
	import CoachingStyleSelector from '$lib/components/education/CoachingStyleSelector.svelte';
	import ChallengeSettings from '$lib/components/education/ChallengeSettings.svelte';
	import { EDU_FIELD_CLASS, eduSegmentClass } from '$lib/components/education/styles';
	import { formatDateTimeInput, getClassroomDisplayName, resolveErrorMessage } from '$lib/utils/education';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let classrooms = [];
	let selectedClassroomIds = new Set();
	let title = '';
	let description = '';
	let dueAt = '';
	let scoreMax = '100';
	let coachingStyle: CoachingStyle = 'balanced';
	let challengeEnabled = false;
	let challengeRounds = 3;
	let challengeFocusKeys: string[] = [];
	// 默认维度走词条，教师看到的是母语名称；key 只是后端字段名，教师不填。
	let rubricCriteria = [
		{ key: 'criterion_1', label: t('Ideas'), maxScore: '34' },
		{ key: 'criterion_2', label: t('Structure'), maxScore: '33' },
		{ key: 'criterion_3', label: t('Evidence'), maxScore: '33' }
	];
	let loading = true;
	let saving = false;

	$: dueAtPreview = formatDateTimeInput(dueAt);
	let loadError = '';

	const toggleClassroom = (id: string) => {
		const next = new Set(selectedClassroomIds);
		if (next.has(id)) {
			next.delete(id);
		} else {
			next.add(id);
		}
		selectedClassroomIds = next;
	};

	onMount(async () => {
		try {
			classrooms = await getTeacherClassrooms(localStorage.token);
			const params = get(page).url.searchParams;
			const presetClassroomId = params.get('classroomId');
			const duplicateFromId = params.get('from');
			// 看板上「以此为下次的质疑焦点」带过来的。放在复制之后覆盖，
			// 因为焦点只有配着同一套评分维度才说得通。
			const presetChallengeFocus = params.get('challengeFocus');

			if (duplicateFromId) {
				try {
					const source = await getTeacherAssignment(localStorage.token, duplicateFromId);
					title = source.assignment.title ?? '';
					description = source.assignment.description ?? '';
					scoreMax = String(source.assignment.score_max);
					coachingStyle = source.assignment.coaching_style;
					challengeEnabled = source.assignment.challenge_enabled ?? false;
					challengeRounds = source.assignment.challenge_rounds ?? 3;
					challengeFocusKeys = [...(source.assignment.challenge_focus_keys ?? [])];
					rubricCriteria = source.assignment.rubric_schema.criteria.map((criterion) => ({
						key: criterion.key,
						label: criterion.label,
						maxScore: String(criterion.max_score)
					}));
					if (source.assignment.classroom_id) {
						selectedClassroomIds = new Set([source.assignment.classroom_id]);
					}
				} catch (error) {
					toast.error(resolveErrorMessage(error, t));
				}
			}

			if (presetChallengeFocus) {
				challengeEnabled = true;
				challengeFocusKeys = [presetChallengeFocus];
			}

			if (selectedClassroomIds.size === 0) {
				const initial = presetClassroomId || classrooms[0]?.classroom?.id;
				if (initial) {
					selectedClassroomIds = new Set([initial]);
				}
			}
		} catch (error) {
			loadError = resolveErrorMessage(error, t);
			toast.error(loadError);
		} finally {
			loading = false;
		}
	});

	const submit = async () => {
		if (!title.trim()) {
			toast.error(t('Assignment title is required.'));
			return;
		}
		if (selectedClassroomIds.size === 0) {
			toast.error(t('Classroom is required.'));
			return;
		}
		if (!dueAt) {
			toast.error(t('Assignment due time is required.'));
			return;
		}
		const parsedScoreMax = Number(scoreMax);
		if (!Number.isInteger(parsedScoreMax) || parsedScoreMax <= 0) {
			toast.error(t('Maximum score must be a positive whole number.'));
			return;
		}
		const parsedCriteria = rubricCriteria.map((criterion) => ({
			key: criterion.key.trim(),
			label: criterion.label.trim(),
			max_score: Number(criterion.maxScore)
		}));
		if (
			parsedCriteria.some(
				(criterion) =>
					!criterion.label || !Number.isInteger(criterion.max_score) || criterion.max_score <= 0
			)
		) {
			toast.error(t('Every rubric criterion needs a name and a positive whole-number maximum.'));
			return;
		}
		if (parsedCriteria.reduce((sum, criterion) => sum + criterion.max_score, 0) !== parsedScoreMax) {
			toast.error(t('Rubric maximum scores must add up to the assignment maximum.'));
			return;
		}

		saving = true;
		try {
			const assignments = await createAssignment(localStorage.token, {
				title: title.trim(),
				description: description.trim() || undefined,
				classroom_ids: [...selectedClassroomIds],
				due_at: Math.floor(new Date(dueAt).getTime() / 1000),
				score_max: parsedScoreMax,
				coaching_style: coachingStyle,
				challenge_enabled: challengeEnabled,
				challenge_rounds: challengeRounds,
				challenge_focus_keys: challengeEnabled ? challengeFocusKeys : [],
				rubric_schema: { criteria: parsedCriteria }
			});
			toast.success(
				assignments.length > 1
					? t('Assignment published to {{count}} classrooms.', { count: assignments.length })
					: t('Assignment created.')
			);
			if (assignments.length === 1) {
				goto(`/teacher/assignments/${assignments[0].id}`);
			} else {
				goto('/teacher/assignments');
			}
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			saving = false;
		}
	};
</script>

<TeacherPageShell
	crumbs={[{ label: $i18n.t('Teaching') }, { label: $i18n.t('Assignments'), href: '/teacher/assignments' }]}
	title={$i18n.t('Create Assignment')}
>
	<div class="mx-auto max-w-4xl px-4 py-8">
		<TeacherSectionNav />

	<div class="mb-6 flex flex-wrap items-end justify-end gap-3">
		<EduButton on:click={() => goto('/teacher/assignments')}>
			{$i18n.t('Back to Assignments')}
		</EduButton>
	</div>

	{#if loadError}
		<EduStateCard tone="error">{loadError}</EduStateCard>
	{:else if loading}
		<EduStateCard>{$i18n.t('Loading classrooms...')}</EduStateCard>
	{:else}
		<EduCard padding="lg">
			<div class="grid gap-4">
				<div>
					<div class="mb-2 flex items-center justify-between">
						<div class="text-sm font-semibold">{$i18n.t('Classrooms')}</div>
						<div class="text-xs text-gray-400">
							{$i18n.t('{{count}} selected', { count: selectedClassroomIds.size })}
						</div>
					</div>
					<div class="flex flex-wrap gap-2">
						{#each classrooms as item}
							<button
								type="button"
								class={eduSegmentClass(selectedClassroomIds.has(item.classroom.id))}
								on:click={() => toggleClassroom(item.classroom.id)}
							>
								{getClassroomDisplayName(item.classroom.name, t)}
							</button>
						{/each}
					</div>
					<div class="mt-2 text-xs text-gray-400">
						{$i18n.t('Select one or more classrooms; the assignment is published to each.')}
					</div>
				</div>
				<div>
					<div class="mb-2 text-sm font-semibold">{$i18n.t('Assignment title')}</div>
					<input
						bind:value={title}
						class="w-full {EDU_FIELD_CLASS}"
						placeholder={$i18n.t('Academic Argument 1')}
					/>
				</div>
				<div>
					<div class="mb-2 text-sm font-semibold">{$i18n.t('Assignment description')}</div>
					<textarea
						bind:value={description}
						class="min-h-32 w-full {EDU_FIELD_CLASS}"
						placeholder={$i18n.t('Write a short academic argument.')}
					></textarea>
				</div>
				<div>
					<div class="mb-2 text-sm font-semibold">{$i18n.t('Due At')}</div>
					<EduDateTimeField bind:value={dueAt} required className="w-full {EDU_FIELD_CLASS}" />
					{#if dueAtPreview}
						<div class="mt-1.5 text-xs text-gray-400 dark:text-gray-500">{dueAtPreview}</div>
					{/if}
				</div>
				<div>
					<div class="mb-2 text-sm font-semibold">{$i18n.t('Maximum Score')}</div>
					<input
						bind:value={scoreMax}
						type="number"
						min="1"
						step="1"
						required
						class="w-full {EDU_FIELD_CLASS}"
					/>
				</div>
				<CoachingStyleSelector bind:value={coachingStyle} />
				<RubricCriteriaEditor bind:criteria={rubricCriteria} {scoreMax} />
				<ChallengeSettings
					criteria={rubricCriteria}
					bind:enabled={challengeEnabled}
					bind:rounds={challengeRounds}
					bind:focusKeys={challengeFocusKeys}
				/>
				<div class="flex justify-end">
					<EduButton variant="primary" on:click={submit} disabled={saving}>
						{saving ? $i18n.t('Creating...') : $i18n.t('Create Assignment')}
					</EduButton>
				</div>
			</div>
		</EduCard>
	{/if}
	</div>
</TeacherPageShell>
