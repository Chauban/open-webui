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
		getTeacherAssignment,
		getTeacherClassrooms,
		getTeacherReflectionQuestionSets,
		updateAssignment
	} from '$lib/apis/education';
	import type { ReflectionQuestionSet } from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import AssignmentForm from '$lib/components/education/AssignmentForm.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import { assignmentTabs } from '$lib/components/education/teacher-nav';
	import { buildAssignmentPayload, type AssignmentDraft } from '$lib/utils/assignment-form';
	import { resolveErrorMessage, toLocalDateTimeInput } from '$lib/utils/education';

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	const assignmentId = $page.params.assignmentId;

	let item = null;
	let classrooms = [];
	let reflectionQuestionSets: ReflectionQuestionSet[] = [];
	let draft: AssignmentDraft | null = null;
	let classroomId = '';
	let loading = true;
	let loadError = '';
	let saving = false;
	let showDeleteConfirm = false;

	$: hasSubmissions = (item?.submission_count ?? 0) > 0;

	const syncDraft = () => {
		const assignment = item.assignment;
		classroomId = assignment.classroom_id || '';
		draft = {
			title: assignment.title || '',
			description: assignment.description || '',
			dueAt: assignment.due_at ? toLocalDateTimeInput(assignment.due_at) : '',
			scoreMax: String(assignment.score_max),
			coachingStyle: assignment.coaching_style,
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
			}))
		};
	};

	const loadData = async () => {
		const [assignmentItem, teacherClassrooms, questionSets] = await Promise.all([
			getTeacherAssignment(localStorage.token, assignmentId),
			getTeacherClassrooms(localStorage.token),
			getTeacherReflectionQuestionSets(localStorage.token).catch((error) => {
				console.error(error);
				return [];
			})
		]);
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
		const { payload, error } = buildAssignmentPayload(draft, t);
		if (error) {
			toast.error(error);
			return;
		}
		saving = true;
		try {
			await updateAssignment(localStorage.token, assignmentId, {
				...payload,
				classroom_id: classroomId
			});
			await loadData();
			toast.success(t('Assignment updated.'));
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
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
	<div class="mx-auto max-w-5xl px-4 py-6">
		{#if loading}
			<EduStateCard>{$i18n.t('Loading assignment...')}</EduStateCard>
		{:else if loadError}
			<EduStateCard tone="error">{loadError}</EduStateCard>
		{:else if draft}
			<AssignmentForm
				bind:draft
				bind:classroomId
				{classrooms}
				{hasSubmissions}
				{reflectionQuestionSets}
				currentAssignmentId={assignmentId}
			>
				<svelte:fragment slot="footer">
					<div
						class="sticky bottom-0 z-10 flex justify-end border-t border-gray-100 bg-white/90 py-3 backdrop-blur dark:border-gray-850 dark:bg-gray-900/90"
					>
						<EduButton variant="primary" disabled={saving} on:click={save}>
							{saving ? $i18n.t('Saving...') : $i18n.t('Save Changes')}
						</EduButton>
					</div>

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

	<ConfirmDialog
		bind:show={showDeleteConfirm}
		title={$i18n.t('Delete Assignment')}
		message={$i18n.t(
			'Only assignments without any student activity can be deleted. This cannot be undone. Continue?'
		)}
		on:confirm={remove}
	/>
</TeacherPageShell>
