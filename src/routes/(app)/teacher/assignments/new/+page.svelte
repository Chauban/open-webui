<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import {
		createAssignment,
		getTeacherAssignment,
		getTeacherClassrooms,
		getTeacherReflectionQuestionSets
	} from '$lib/apis/education';
	import type { ReflectionQuestionSet } from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import AssignmentForm from '$lib/components/education/AssignmentForm.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import {
		cloneReflectionQuestions,
		getDefaultReflectionQuestions
	} from '$lib/utils/reflection-questions';
	import { buildAssignmentPayload, type AssignmentDraft } from '$lib/utils/assignment-form';
	import { resolveErrorMessage } from '$lib/utils/education';

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let classrooms = [];
	let selectedClassroomIds = new Set<string>();
	let reflectionQuestionSets: ReflectionQuestionSet[] = [];
	let reflectionNotice = '';
	// 默认维度走词条，教师看到的是母语名称；key 只是后端字段名，教师不填。
	let draft: AssignmentDraft = {
		title: '',
		description: '',
		dueAt: '',
		scoreMax: '100',
		coachingStyle: 'balanced',
		challengeEnabled: false,
		challengeRounds: 3,
		challengeFocusKeys: [],
		reflectionQuestions: [],
		rubricCriteria: [
			{ key: 'criterion_1', label: t('Ideas'), maxScore: '34' },
			{ key: 'criterion_2', label: t('Structure'), maxScore: '33' },
			{ key: 'criterion_3', label: t('Evidence'), maxScore: '33' }
		]
	};
	let loading = true;
	let saving = false;
	let loadError = '';

	onMount(async () => {
		try {
			// 以往题组读不出来不该挡住建作业，退回默认题即可。
			const [teacherClassrooms, questionSets] = await Promise.all([
				getTeacherClassrooms(localStorage.token),
				getTeacherReflectionQuestionSets(localStorage.token).catch((error) => {
					console.error(error);
					return [];
				})
			]);
			classrooms = teacherClassrooms;
			reflectionQuestionSets = questionSets;
			// 教师大多一门课一套反思，所以默认沿用最近一份作业的题；第一次出题才给推荐题。
			if (questionSets.length > 0) {
				draft.reflectionQuestions = cloneReflectionQuestions(questionSets[0].questions);
				reflectionNotice = t(
					'Pre-filled with the questions from your last assignment "{{title}}". Edit them, import another set, or restore defaults.',
					{ title: questionSets[0].assignment_title }
				);
			} else {
				draft.reflectionQuestions = getDefaultReflectionQuestions(t);
				reflectionNotice = t(
					'Pre-filled with recommended questions. Add, remove, or rewrite them to fit this assignment.'
				);
			}
			const params = get(page).url.searchParams;
			const presetClassroomId = params.get('classroomId');
			const duplicateFromId = params.get('from');
			// 分析页上「以此为下次的质疑焦点」带过来的。放在复制之后覆盖，
			// 因为焦点只有配着同一套评分维度才说得通。
			const presetChallengeFocus = params.get('challengeFocus');

			if (duplicateFromId) {
				try {
					const source = await getTeacherAssignment(localStorage.token, duplicateFromId);
					draft = {
						title: source.assignment.title ?? '',
						description: source.assignment.description ?? '',
						dueAt: '',
						scoreMax: String(source.assignment.score_max),
						coachingStyle: source.assignment.coaching_style,
						challengeEnabled: source.assignment.challenge_enabled ?? false,
						challengeRounds: source.assignment.challenge_rounds ?? 3,
						challengeFocusKeys: [...(source.assignment.challenge_focus_keys ?? [])],
						reflectionQuestions: cloneReflectionQuestions(
							source.assignment.reflection_questions ?? []
						),
						rubricCriteria: source.assignment.rubric_schema.criteria.map((criterion) => ({
							key: criterion.key,
							label: criterion.label,
							maxScore: String(criterion.max_score)
						}))
					};
					reflectionNotice = t('Copied the reflection questions from "{{title}}".', {
						title: source.assignment.title
					});
					if (source.assignment.classroom_id) {
						selectedClassroomIds = new Set([source.assignment.classroom_id]);
					}
				} catch (error) {
					toast.error(resolveErrorMessage(error, t));
				}
			}

			if (presetChallengeFocus) {
				draft.challengeEnabled = true;
				draft.challengeFocusKeys = [presetChallengeFocus];
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
		if (selectedClassroomIds.size === 0) {
			toast.error(t('Classroom is required.'));
			return;
		}
		const { payload, error } = buildAssignmentPayload(draft, t);
		if (error) {
			toast.error(error);
			return;
		}

		saving = true;
		try {
			const assignments = await createAssignment(localStorage.token, {
				...payload,
				description: payload.description || undefined,
				classroom_ids: [...selectedClassroomIds]
			});
			toast.success(
				assignments.length > 1
					? t('Assignment published to {{count}} classrooms.', { count: assignments.length })
					: t('Assignment created.')
			);
			goto(assignments.length === 1 ? `/teacher/assignments/${assignments[0].id}` : '/teacher/assignments');
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			saving = false;
		}
	};
</script>

<TeacherPageShell
	crumbs={[{ label: $i18n.t('Assignments'), href: '/teacher/assignments' }]}
	title={$i18n.t('Create Assignment')}
>
	<div class="mx-auto max-w-5xl px-4 py-6">
		{#if loadError}
			<EduStateCard tone="error">{loadError}</EduStateCard>
		{:else if loading}
			<EduStateCard>{$i18n.t('Loading classrooms...')}</EduStateCard>
		{:else}
			<AssignmentForm
				bind:draft
				bind:selectedClassroomIds
				multiClassroom
				{classrooms}
				{reflectionQuestionSets}
				{reflectionNotice}
			>
				<div
					slot="footer"
					class="sticky bottom-0 flex justify-end gap-2 border-t border-gray-100 bg-white/90 py-3 backdrop-blur dark:border-gray-850 dark:bg-gray-900/90"
				>
					<EduButton on:click={() => goto('/teacher/assignments')}>{$i18n.t('Cancel')}</EduButton>
					<EduButton variant="primary" on:click={submit} disabled={saving}>
						{saving ? $i18n.t('Creating...') : $i18n.t('Create Assignment')}
					</EduButton>
				</div>
			</AssignmentForm>
		{/if}
	</div>
</TeacherPageShell>
