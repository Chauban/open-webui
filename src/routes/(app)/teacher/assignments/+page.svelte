<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { getTeacherAssignments } from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	const getClassroomDisplayName = (name: string) =>
		name?.trim() === 'Default Classroom' ? t('Default Classroom') : name;
	const getAssignmentStatusLabel = (value: string) =>
		({
			active: t('Active'),
			archived: t('Archived')
		})[value] || value;

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
				label: getClassroomDisplayName(item.classroom.name)
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
			item.assignment.status === selectedStatus ||
			(selectedStatus === 'needs_review' && item.submission_count > 0);
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
		<div class="mb-8 text-sm text-gray-500">
			{$i18n.t('View every assignment across classrooms, then jump into submissions or analytics.')}
		</div>

		<TeacherSectionNav />

		<div class="mb-8 grid gap-3 rounded-3xl border border-gray-200 bg-white p-5 md:grid-cols-4">
			<select class="rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none" bind:value={selectedClassroom}>
				{#each classroomOptions as option}
					<option value={option.value}>{option.label}</option>
				{/each}
			</select>
			<select class="rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none" bind:value={selectedStatus}>
				<option value="all">{$i18n.t('All')}</option>
				<option value="active">{$i18n.t('Active')}</option>
				<option value="archived">{$i18n.t('Archived')}</option>
				<option value="needs_review">{$i18n.t('Has submissions')}</option>
			</select>
			<input
				bind:value={keyword}
				class="rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none"
				placeholder={$i18n.t('Search assignments')}
			/>
			<select class="rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none" bind:value={sortBy}>
				<option value="latest_activity">{$i18n.t('Sort by Latest')}</option>
				<option value="suspected">{$i18n.t('Sort by Suspected Imports')}</option>
				<option value="burst">{$i18n.t('Sort by Large Bursts')}</option>
				<option value="rewrite">{$i18n.t('Sort by Rewrite Ratio')}</option>
			</select>
		</div>
		<div class="mb-8 flex flex-wrap gap-2">
			<button
				class={`rounded-full border px-4 py-2 text-sm transition ${
					onlySuspected ? 'border-rose-300 bg-rose-50 text-rose-700' : 'border-gray-300 bg-white text-gray-700'
				}`}
				on:click={() => (onlySuspected = !onlySuspected)}
			>
				{$i18n.t('Only Suspected Imports')}
			</button>
			<button
				class={`rounded-full border px-4 py-2 text-sm transition ${
					onlyBursts ? 'border-amber-300 bg-amber-50 text-amber-700' : 'border-gray-300 bg-white text-gray-700'
				}`}
				on:click={() => (onlyBursts = !onlyBursts)}
			>
				{$i18n.t('Only Large Bursts')}
			</button>
		</div>

		{#if loadError}
			<div class="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
				{loadError}
			</div>
		{:else if loading}
			<div class="rounded-3xl border border-gray-200 bg-white p-6 text-sm text-gray-500">
				{$i18n.t('Loading assignments...')}
			</div>
		{:else if filteredAssignments.length === 0}
			<div class="rounded-3xl border border-gray-200 bg-white p-6 text-sm text-gray-500">
				{assignments.length === 0 ? $i18n.t('No assignments yet.') : $i18n.t('No assignments match the current filters.')}
			</div>
		{:else}
			<div class="grid gap-4">
				{#each filteredAssignments as item}
					<div class="rounded-3xl border border-gray-200 bg-white p-5">
						<div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
							<div>
								<div class="text-lg font-semibold text-gray-900">{item.assignment.title}</div>
								<div class="mt-1 text-sm text-gray-500">
									{item.assignment.description || $i18n.t('No description')}
								</div>
								<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
									<div>
										{$i18n.t('Classroom')}:
										{item.classroom ? getClassroomDisplayName(item.classroom.name) : t('Unknown')}
									</div>
									<div>{$i18n.t('Students')}: {item.student_count}</div>
									<div>{$i18n.t('Submissions')}: {item.submission_count}</div>
									<div>{$i18n.t('Status')}: {getAssignmentStatusLabel(item.assignment.status)}</div>
									<div>
										{$i18n.t('Latest Activity')}:
										{item.latest_submission_at
											? new Date(item.latest_submission_at * 1000).toLocaleString()
											: t('No submissions yet.')}
									</div>
								</div>
								<div class="mt-3 flex flex-wrap gap-2 text-xs">
									<div class="rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-sky-700">
										{$i18n.t('AI pasted')}: {item.risk_summary?.ai_pasted_chars ?? 0}
									</div>
									<div class="rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-gray-700">
										{$i18n.t('AI inserted')}: {item.risk_summary?.ai_inserted_chars ?? 0}
									</div>
									<div class="rounded-full border border-rose-200 bg-rose-50 px-3 py-1.5 text-rose-700">
										{$i18n.t('Suspected Unmarked Imports')}: {item.risk_summary?.suspected_unmarked_import_count ?? 0}
									</div>
									<div class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-amber-700">
										{$i18n.t('Large Bursts')}: {item.risk_summary?.burst_count ?? 0}
									</div>
								</div>
							</div>

							<div class="flex flex-wrap gap-2">
								<button
									class="rounded-full border border-gray-300 px-3 py-2 text-sm"
									on:click={() => goto(`/teacher/assignments/${item.assignment.id}`)}
								>
									{$i18n.t('Open')}
								</button>
								<button
									class="rounded-full border border-gray-300 px-3 py-2 text-sm"
									on:click={() => copyWriteLink(item.assignment.id)}
								>
									{$i18n.t('Copy Student Link')}
								</button>
								<button
									class="rounded-full border border-gray-300 px-3 py-2 text-sm"
									on:click={() => goto(`/teacher/assignments/${item.assignment.id}/submissions`)}
								>
									{$i18n.t('Submissions')}
								</button>
								<button
									class="rounded-full border border-gray-300 px-3 py-2 text-sm"
									on:click={() => goto(`/teacher/assignments/${item.assignment.id}/dashboard`)}
								>
									{$i18n.t('Dashboard')}
								</button>
							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</TeacherPageShell>
