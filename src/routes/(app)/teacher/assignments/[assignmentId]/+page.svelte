<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import {
		archiveAssignment,
		deleteAssignment,
		getTeacherAssignment,
		getTeacherClassrooms,
		updateAssignment
	} from '$lib/apis/education';
	import type { CoachingStyle } from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduStatCard from '$lib/components/education/EduStatCard.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import RubricCriteriaEditor from '$lib/components/education/RubricCriteriaEditor.svelte';
	import CoachingStyleSelector from '$lib/components/education/CoachingStyleSelector.svelte';
	import { EDU_FIELD_CLASS } from '$lib/components/education/styles';
	import {
		formatDateTimeInput,
		formatEpoch,
		getAssignmentStatusLabel,
		getClassroomDisplayName,
		resolveErrorMessage,
		toLocalDateTimeInput
	} from '$lib/utils/education';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let item = null;
	let classrooms = [];
	let loading = true;
	let loadError = '';
	let saving = false;
	let title = '';
	let description = '';
	let classroomId = '';
	let status = 'active';
	let dueAt = '';
	let scoreMax = '';
	let coachingStyle: CoachingStyle = 'balanced';
	let rubricCriteria = [];
	let showArchiveConfirm = false;
	let showDeleteConfirm = false;

	const assignmentId = () => $page.params.assignmentId;

	$: isPastDue =
		item?.assignment?.status === 'active' &&
		item?.assignment?.due_at &&
		item.assignment.due_at * 1000 < Date.now();
	$: dueAtPreview = formatDateTimeInput(dueAt);

	// datetime-local expects a LOCAL "YYYY-MM-DDTHH:mm" string; toISOString() would shift to UTC.

	const copyWriteLink = async () => {
		const link = `${window.location.origin}/assignments/${assignmentId()}/write`;
		try {
			await navigator.clipboard.writeText(link);
			toast.success(t('Write link copied.'));
		} catch {
			toast.error(t('Failed to copy write link.'));
		}
	};

	const syncForm = () => {
		if (!item) return;
		title = item.assignment.title || '';
		description = item.assignment.description || '';
		classroomId = item.assignment.classroom_id || '';
		status = item.assignment.status || 'active';
		dueAt = item.assignment.due_at ? toLocalDateTimeInput(item.assignment.due_at) : '';
		scoreMax = String(item.assignment.score_max);
		coachingStyle = item.assignment.coaching_style;
		rubricCriteria = item.assignment.rubric_schema.criteria.map((criterion) => ({
			key: criterion.key,
			label: criterion.label,
			maxScore: String(criterion.max_score)
		}));
	};

	const loadData = async () => {
		const [assignmentItem, teacherClassrooms] = await Promise.all([
			getTeacherAssignment(localStorage.token, assignmentId()),
			getTeacherClassrooms(localStorage.token)
		]);
		classrooms = teacherClassrooms;
		item = assignmentItem;
		syncForm();
	};

	const saveAssignment = async () => {
		if (!title.trim()) {
			toast.error(t('Assignment title is required.'));
			return;
		}
		if (!classroomId) {
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
			await updateAssignment(localStorage.token, assignmentId(), {
				title: title.trim(),
				description: description.trim(),
				classroom_id: classroomId,
				status,
				due_at: Math.floor(new Date(dueAt).getTime() / 1000),
				score_max: parsedScoreMax,
				coaching_style: coachingStyle,
				rubric_schema: { criteria: parsedCriteria }
			});
			await loadData();
			toast.success(t('Assignment updated.'));
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			saving = false;
		}
	};

	const archiveCurrentAssignment = async () => {
		try {
			await archiveAssignment(localStorage.token, assignmentId());
			await loadData();
			toast.success(t('Assignment archived.'));
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		}
	};

	const deleteCurrentAssignment = async () => {
		try {
			await deleteAssignment(localStorage.token, assignmentId());
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

<TeacherPageShell title="Assignments">
	{#if loading}
		<div class="mx-auto max-w-6xl px-4 py-8 text-sm text-gray-500 dark:text-gray-400">{$i18n.t('Loading assignment...')}</div>
	{:else if loadError}
		<div class="mx-auto max-w-3xl px-4 py-16">
			<EduStateCard tone="error">{loadError}</EduStateCard>
		</div>
	{:else}
		<div class="mx-auto max-w-6xl px-4 py-8">
			<TeacherSectionNav />

			<div class="mb-6 flex flex-wrap items-end justify-between gap-3">
				<div>
					<div class="mb-2 text-sm text-gray-500 dark:text-gray-400">{$i18n.t('Teaching')} / {$i18n.t('Assignments')}</div>
					<h1 class="text-3xl font-semibold">{item.assignment.title}</h1>
					<div class="mt-2 text-sm text-gray-500 dark:text-gray-400">
						{item.classroom ? getClassroomDisplayName(item.classroom.name, t) : t('Unknown classroom')}
					</div>
				</div>
				<div class="flex flex-wrap gap-2">
					<EduButton on:click={() => goto('/teacher/assignments')}>
						{$i18n.t('Back to Assignments')}
					</EduButton>
					<EduButton on:click={copyWriteLink}>
						{$i18n.t('Copy Student Link')}
					</EduButton>
					<EduButton on:click={() => goto(`/teacher/assignments/new?from=${item.assignment.id}`)}>
						{$i18n.t('Duplicate')}
					</EduButton>
				</div>
			</div>

			<div class="mb-8 grid gap-4 md:grid-cols-4">
				<EduStatCard label="Students" value={item.student_count} />
				<EduStatCard label="Submissions" value={item.submission_count} />
				<EduCard>
					<div class="text-xs uppercase tracking-[0.16em] text-gray-500 dark:text-gray-400">{$i18n.t('Status')}</div>
					<div class="mt-2 text-sm font-medium {isPastDue ? 'text-rose-600 dark:text-rose-400' : 'text-gray-900 dark:text-gray-100'}">
						{isPastDue ? $i18n.t('Past Due') : getAssignmentStatusLabel(item.assignment.status, t)}
					</div>
				</EduCard>
				<EduCard>
					<div class="text-xs uppercase tracking-[0.16em] text-gray-500 dark:text-gray-400">{$i18n.t('Due At')}</div>
					<div class="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">
						{item.assignment.due_at ? formatEpoch(item.assignment.due_at) : t('Not set')}
					</div>
				</EduCard>
			</div>

			<div class="mb-8 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
				<EduCard>
					<div class="mb-4 text-sm font-semibold">{$i18n.t('Assignment Details')}</div>
					<div class="grid gap-4">
						<div>
							<div class="mb-2 text-sm font-medium">{$i18n.t('Title')}</div>
							<input bind:value={title} class="w-full {EDU_FIELD_CLASS}" />
						</div>
						<div>
							<div class="mb-2 text-sm font-medium">{$i18n.t('Description')}</div>
							<textarea bind:value={description} class="min-h-28 w-full {EDU_FIELD_CLASS}"></textarea>
						</div>
						<div class="grid gap-4 md:grid-cols-4">
							<div>
								<div class="mb-2 text-sm font-medium">{$i18n.t('Classroom')}</div>
								<select bind:value={classroomId} class="w-full {EDU_FIELD_CLASS}">
									{#each classrooms as classroom}
										<option value={classroom.classroom.id}>{getClassroomDisplayName(classroom.classroom.name, t)}</option>
									{/each}
								</select>
							</div>
							<div>
								<div class="mb-2 text-sm font-medium">{$i18n.t('Status')}</div>
								<select bind:value={status} class="w-full {EDU_FIELD_CLASS}">
									<option value="active">{$i18n.t('Ongoing')}</option>
									<option value="archived">{$i18n.t('Archived')}</option>
								</select>
							</div>
							<div>
								<div class="mb-2 text-sm font-medium">{$i18n.t('Due At')}</div>
								<input bind:value={dueAt} type="datetime-local" required class="w-full {EDU_FIELD_CLASS}" />
								{#if dueAtPreview}
									<div class="mt-1.5 text-xs text-gray-400 dark:text-gray-500">{dueAtPreview}</div>
								{/if}
							</div>
							<div>
								<div class="mb-2 text-sm font-medium">{$i18n.t('Maximum Score')}</div>
								<input
									bind:value={scoreMax}
									type="number"
									min="1"
									step="1"
									disabled={item.submission_count > 0}
									class="w-full {EDU_FIELD_CLASS} disabled:opacity-60"
								/>
								{#if item.submission_count > 0}
									<div class="mt-1 text-xs text-gray-400">
										{$i18n.t('Maximum score is locked after the first submission.')}
									</div>
								{/if}
							</div>
						</div>
						<CoachingStyleSelector bind:value={coachingStyle} />
						<RubricCriteriaEditor
							bind:criteria={rubricCriteria}
							{scoreMax}
							disabled={item.submission_count > 0}
							lockedHint={item.submission_count > 0
								? $i18n.t('Rubric criteria are locked after the first submission.')
								: ''}
						/>
						<div class="flex flex-wrap justify-between gap-2">
							<div class="flex flex-wrap gap-2">
								<EduButton variant="danger" on:click={() => (showArchiveConfirm = true)}>
									{$i18n.t('Archive')}
								</EduButton>
								<EduButton variant="danger" on:click={() => (showDeleteConfirm = true)}>
									{$i18n.t('Delete')}
								</EduButton>
							</div>
							<EduButton variant="primary" disabled={saving} on:click={saveAssignment}>
								{saving ? $i18n.t('Saving...') : $i18n.t('Save Changes')}
							</EduButton>
						</div>
					</div>
				</EduCard>

				<div class="grid gap-4 md:grid-cols-1">
					<EduCard
						interactive
						on:click={() => goto(`/teacher/assignments/${item.assignment.id}/submissions`)}
					>
						<div class="text-lg font-semibold">{$i18n.t('Submissions')}</div>
						<div class="mt-2 text-sm text-gray-500 dark:text-gray-400">
							{$i18n.t('Review each student submission for this assignment.')}
						</div>
					</EduCard>
					<EduCard
						interactive
						on:click={() => goto(`/teacher/assignments/${item.assignment.id}/dashboard`)}
					>
						<div class="text-lg font-semibold">{$i18n.t('Dashboard')}</div>
						<div class="mt-2 text-sm text-gray-500 dark:text-gray-400">
							{$i18n.t('Inspect writing-source analytics and reflection coverage.')}
						</div>
					</EduCard>
					<EduCard
						interactive
						on:click={() => goto(`/teacher/classrooms/${item.assignment.classroom_id}`)}
					>
						<div class="text-lg font-semibold">{$i18n.t('Open Classroom')}</div>
						<div class="mt-2 text-sm text-gray-500 dark:text-gray-400">
							{$i18n.t('Return to the classroom that owns this assignment.')}
						</div>
					</EduCard>
				</div>
			</div>
		</div>
	{/if}

	<ConfirmDialog
		bind:show={showArchiveConfirm}
		title={$i18n.t('Archive Assignment')}
		message={$i18n.t(
			'Archiving is one-way and cannot be undone. Students will no longer see this assignment as active. Continue?'
		)}
		on:confirm={archiveCurrentAssignment}
	/>

	<ConfirmDialog
		bind:show={showDeleteConfirm}
		title={$i18n.t('Delete Assignment')}
		message={$i18n.t(
			'Only assignments without any student activity can be deleted. This cannot be undone. Continue?'
		)}
		on:confirm={deleteCurrentAssignment}
	/>
</TeacherPageShell>
