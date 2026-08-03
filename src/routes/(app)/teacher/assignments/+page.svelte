<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { getTeacherAssignments } from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';
	import EduBadge from '$lib/components/education/EduBadge.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import { EDU_FIELD_CLASS, eduFilterClass } from '$lib/components/education/styles';
	import { getAssignmentStatusLabel, getClassroomDisplayName } from '$lib/utils/education';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	const isPastDue = (item) =>
		item.assignment.status === 'active' &&
		item.assignment.due_at &&
		item.assignment.due_at * 1000 < Date.now();

	let assignments = [];
	let loading = true;
	let loadError = '';
	let selectedClassroom = 'all';
	let selectedStatus = 'all';
	let keyword = '';
	let onlySuspected = false;
	let onlyBursts = false;
	let sortBy = 'latest_activity';

	$: classroomOptions = [
		{ value: 'all', label: t('All Classrooms') },
		...assignments
			.filter((item, index, list) => item.classroom && list.findIndex((entry) => entry.classroom?.id === item.classroom.id) === index)
			.map((item) => ({
				value: item.classroom.id,
				label: getClassroomDisplayName(item.classroom.name, t)
			}))
	];

	$: filteredAssignments = assignments.filter((item) => {
		const matchesClassroom =
			selectedClassroom === 'all' || item.classroom?.id === selectedClassroom;
		const normalizedKeyword = keyword.trim().toLowerCase();
		const matchesKeyword =
			!normalizedKeyword ||
			item.assignment.title?.toLowerCase().includes(normalizedKeyword) ||
			item.assignment.description?.toLowerCase().includes(normalizedKeyword) ||
			item.classroom?.name?.toLowerCase().includes(normalizedKeyword);
		const matchesStatus =
			selectedStatus === 'all' ||
			(selectedStatus === 'past_due'
				? isPastDue(item)
				: item.assignment.status === selectedStatus ||
					(selectedStatus === 'needs_review' && item.submission_count > 0));
		const matchesSuspected = !onlySuspected || (item.risk_summary?.suspected_unmarked_import_count ?? 0) > 0;
		const matchesBursts = !onlyBursts || (item.risk_summary?.burst_count ?? 0) > 0;

		return matchesClassroom && matchesKeyword && matchesStatus && matchesSuspected && matchesBursts;
	}).sort((a, b) => {
		if (sortBy === 'suspected') {
			return (b.risk_summary?.suspected_unmarked_import_count ?? 0) - (a.risk_summary?.suspected_unmarked_import_count ?? 0);
		}
		if (sortBy === 'burst') {
			return (b.risk_summary?.burst_count ?? 0) - (a.risk_summary?.burst_count ?? 0);
		}
		if (sortBy === 'rewrite') {
			return (b.risk_summary?.average_rewrite_ratio ?? 0) - (a.risk_summary?.average_rewrite_ratio ?? 0);
		}
		return (b.latest_submission_at ?? 0) - (a.latest_submission_at ?? 0);
	});

	const loadData = async () => {
		loading = true;
		loadError = '';
		try {
			assignments = await getTeacherAssignments(localStorage.token);
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		} finally {
			loading = false;
		}
	};

	const copyWriteLink = async (assignmentId: string) => {
		const link = `${window.location.origin}/assignments/${assignmentId}/write`;
		try {
			await navigator.clipboard.writeText(link);
			toast.success(t('Write link copied.'));
		} catch {
			toast.error(t('Failed to copy write link.'));
		}
	};

	onMount(async () => {
		await loadData();
	});
</script>

<TeacherPageShell title="Assignments">
	<div class="mx-auto max-w-6xl px-4 py-8">
		<div class="mb-8 flex flex-wrap items-center justify-between gap-3">
			<div class="text-sm text-gray-500 dark:text-gray-400">
				{$i18n.t('View every assignment across classrooms, then jump into submissions or analytics.')}
			</div>
			<EduButton variant="primary" on:click={() => goto('/teacher/assignments/new')}>
				{$i18n.t('New Assignment')}
			</EduButton>
		</div>

		<TeacherSectionNav />

		<EduCard class="mb-8 grid gap-3 md:grid-cols-4">
			<select class={EDU_FIELD_CLASS} bind:value={selectedClassroom}>
				{#each classroomOptions as option}
					<option value={option.value}>{option.label}</option>
				{/each}
			</select>
			<select class={EDU_FIELD_CLASS} bind:value={selectedStatus}>
				<option value="all">{$i18n.t('All')}</option>
				<option value="active">{$i18n.t('Active')}</option>
				<option value="past_due">{$i18n.t('Past Due')}</option>
				<option value="archived">{$i18n.t('Archived')}</option>
				<option value="needs_review">{$i18n.t('Has submissions')}</option>
			</select>
			<input
				bind:value={keyword}
				class={EDU_FIELD_CLASS}
				placeholder={$i18n.t('Search assignments')}
			/>
			<select class={EDU_FIELD_CLASS} bind:value={sortBy}>
				<option value="latest_activity">{$i18n.t('Sort by Latest')}</option>
				<option value="suspected">{$i18n.t('Sort by Suspected Imports')}</option>
				<option value="burst">{$i18n.t('Sort by Large Bursts')}</option>
				<option value="rewrite">{$i18n.t('Sort by Rewrite Ratio')}</option>
			</select>
		</EduCard>
		<div class="mb-8 flex flex-wrap gap-2">
			<button
				class={eduFilterClass(onlySuspected, 'rose')}
				on:click={() => (onlySuspected = !onlySuspected)}
			>
				{$i18n.t('Only Suspected Imports')}
			</button>
			<button
				class={eduFilterClass(onlyBursts, 'amber')}
				on:click={() => (onlyBursts = !onlyBursts)}
			>
				{$i18n.t('Only Large Bursts')}
			</button>
		</div>

		{#if loadError}
			<EduStateCard tone="error">{loadError}</EduStateCard>
		{:else if loading}
			<EduStateCard>{$i18n.t('Loading assignments...')}</EduStateCard>
		{:else if filteredAssignments.length === 0}
			<EduStateCard>
				{assignments.length === 0 ? $i18n.t('No assignments yet.') : $i18n.t('No assignments match the current filters.')}
			</EduStateCard>
		{:else}
			<div class="grid gap-4">
				{#each filteredAssignments as item}
					<EduCard>
						<div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
							<div>
								<div class="text-lg font-semibold text-gray-900 dark:text-gray-100">{item.assignment.title}</div>
								<div class="mt-1 text-sm text-gray-500 dark:text-gray-400">
									{item.assignment.description || $i18n.t('No description')}
								</div>
								<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500 dark:text-gray-400">
									<div>
										{$i18n.t('Classroom')}:
										{item.classroom ? getClassroomDisplayName(item.classroom.name, t) : t('Unknown')}
									</div>
									<div>{$i18n.t('Students')}: {item.student_count}</div>
									<div>{$i18n.t('Submissions')}: {item.submission_count}</div>
									<div>
										{$i18n.t('Status')}:
										{#if isPastDue(item)}
											<span class="text-rose-600 dark:text-rose-400">{$i18n.t('Past Due')}</span>
										{:else}
											{getAssignmentStatusLabel(item.assignment.status, t)}
										{/if}
									</div>
									{#if item.assignment.due_at}
										<div>
											{$i18n.t('Due At')}:
											{new Date(item.assignment.due_at * 1000).toLocaleString()}
										</div>
									{/if}
									<div>
										{$i18n.t('Latest Activity')}:
										{item.latest_submission_at
											? new Date(item.latest_submission_at * 1000).toLocaleString()
											: t('No submissions yet.')}
									</div>
								</div>
								<div class="mt-3 flex flex-wrap gap-2 text-xs">
									<EduBadge tone="sky">
										{$i18n.t('AI pasted')}: {item.risk_summary?.ai_pasted_chars ?? 0}
									</EduBadge>
									<EduBadge>
										{$i18n.t('AI inserted')}: {item.risk_summary?.ai_inserted_chars ?? 0}
									</EduBadge>
									<EduBadge tone="rose">
										{$i18n.t('Suspected Unmarked Imports')}: {item.risk_summary
											?.suspected_unmarked_import_count ?? 0}
									</EduBadge>
									<EduBadge tone="amber">
										{$i18n.t('Large Bursts')}: {item.risk_summary?.burst_count ?? 0}
									</EduBadge>
								</div>
							</div>

							<div class="flex flex-wrap gap-2">
								<EduButton on:click={() => goto(`/teacher/assignments/${item.assignment.id}`)}>
									{$i18n.t('Open')}
								</EduButton>
								<EduButton on:click={() => copyWriteLink(item.assignment.id)}>
									{$i18n.t('Copy Student Link')}
								</EduButton>
								<EduButton
									on:click={() => goto(`/teacher/assignments/new?from=${item.assignment.id}`)}
								>
									{$i18n.t('Duplicate')}
								</EduButton>
								<EduButton
									on:click={() => goto(`/teacher/assignments/${item.assignment.id}/submissions`)}
								>
									{$i18n.t('Submissions')}
								</EduButton>
								<EduButton
									on:click={() => goto(`/teacher/assignments/${item.assignment.id}/dashboard`)}
								>
									{$i18n.t('Dashboard')}
								</EduButton>
							</div>
						</div>
					</EduCard>
				{/each}
			</div>
		{/if}
	</div>
</TeacherPageShell>
