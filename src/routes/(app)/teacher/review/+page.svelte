<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import {
		getTeacherReview,
		getEducationNotificationSummary,
		markEducationNotificationsRead
	} from '$lib/apis/education';
	import { educationNotificationSummary } from '$lib/stores';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	const getClassroomDisplayName = (name: string) =>
		name?.trim() === 'Default Classroom' ? t('Default Classroom') : name;
	const getReviewStatusLabel = (value: string) =>
		({
			pending: t('Pending Review'),
			reviewed: t('Reviewed'),
			returned: t('Returned')
		})[value] || value;
	const getRiskTone = (item) => {
		if ((item.analysis_summary?.suspected_unmarked_import_count ?? 0) > 0) return 'rose';
		if ((item.analysis_summary?.burst_count ?? 0) > 0) return 'amber';
		return 'gray';
	};

	let items = [];
	let loading = true;
	let loadError = '';
	let selectedStatus = 'pending';
	let selectedClassroom = 'all';
	let selectedAssignment = 'all';
	let onlySuspected = false;
	let onlyBursts = false;
	let sortBy = 'submitted_at';

	$: classroomOptions = [
		{ value: 'all', label: t('All Classrooms') },
		...items
			.filter(
				(item, index, list) =>
					item.classroom &&
					list.findIndex((entry) => entry.classroom?.id === item.classroom.id) === index
			)
			.map((item) => ({
				value: item.classroom.id,
				label: getClassroomDisplayName(item.classroom.name)
			}))
	];

	$: assignmentOptions = [
		{ value: 'all', label: t('All Assignments') },
		...items
			.filter(
				(item, index, list) =>
					item.assignment &&
					list.findIndex((entry) => entry.assignment.id === item.assignment.id) === index
			)
			.map((item) => ({
				value: item.assignment.id,
				label: item.assignment.title
			}))
	];

	$: filteredItems = items.filter((item) => {
		const matchesStatus = selectedStatus === 'all' ? true : item.review_status === selectedStatus;
		const matchesClassroom =
			selectedClassroom === 'all' ? true : item.classroom?.id === selectedClassroom;
		const matchesAssignment =
			selectedAssignment === 'all' ? true : item.assignment.id === selectedAssignment;
		const matchesSuspected = !onlySuspected || (item.analysis_summary?.suspected_unmarked_import_count ?? 0) > 0;
		const matchesBursts = !onlyBursts || (item.analysis_summary?.burst_count ?? 0) > 0;
		return matchesStatus && matchesClassroom && matchesAssignment && matchesSuspected && matchesBursts;
	}).sort((a, b) => {
		if (sortBy === 'suspected') {
			return (b.analysis_summary?.suspected_unmarked_import_count ?? 0) - (a.analysis_summary?.suspected_unmarked_import_count ?? 0);
		}
		if (sortBy === 'burst') {
			return (b.analysis_summary?.burst_count ?? 0) - (a.analysis_summary?.burst_count ?? 0);
		}
		if (sortBy === 'rewrite') {
			return (b.analysis_summary?.average_rewrite_ratio ?? 0) - (a.analysis_summary?.average_rewrite_ratio ?? 0);
		}
		return (b.submission?.submitted_at ?? 0) - (a.submission?.submitted_at ?? 0);
	});

	onMount(async () => {
		try {
			items = await getTeacherReview(localStorage.token);
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		} finally {
			loading = false;
		}

		try {
			await markEducationNotificationsRead(localStorage.token, {
				types: ['submission_created']
			});
			educationNotificationSummary.set(
				await getEducationNotificationSummary(localStorage.token).catch(() => null)
			);
		} catch (error) {
			console.error('Failed to mark education notifications as read:', error);
		}
	});
</script>

<TeacherPageShell title="Review">
	<div class="mx-auto max-w-6xl px-4 py-8">
		<div class="mb-8 text-sm text-gray-500">
			{$i18n.t('Review pending submissions across classrooms from one queue.')}
		</div>

		<TeacherSectionNav />

		<div class="mb-4 flex flex-wrap gap-2">
			<button
				class={`rounded-full border px-4 py-2 text-sm transition ${
					selectedStatus === 'pending'
						? 'border-black bg-black text-white'
						: 'border-gray-300 bg-white text-gray-700'
				}`}
				on:click={() => (selectedStatus = 'pending')}
			>
				{$i18n.t('To Review')}
			</button>
			<button
				class={`rounded-full border px-4 py-2 text-sm transition ${
					selectedStatus === 'reviewed'
						? 'border-black bg-black text-white'
						: 'border-gray-300 bg-white text-gray-700'
				}`}
				on:click={() => (selectedStatus = 'reviewed')}
			>
				{$i18n.t('Reviewed')}
			</button>
			<button
				class={`rounded-full border px-4 py-2 text-sm transition ${
					selectedStatus === 'returned'
						? 'border-black bg-black text-white'
						: 'border-gray-300 bg-white text-gray-700'
				}`}
				on:click={() => (selectedStatus = 'returned')}
			>
				{$i18n.t('Returned')}
			</button>
			<button
				class={`rounded-full border px-4 py-2 text-sm transition ${
					selectedStatus === 'all'
						? 'border-black bg-black text-white'
						: 'border-gray-300 bg-white text-gray-700'
				}`}
				on:click={() => (selectedStatus = 'all')}
			>
				{$i18n.t('All')}
			</button>
		</div>

		<div class="mb-8 grid gap-3 rounded-3xl border border-gray-200 bg-white p-5 md:grid-cols-4">
			<select class="rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none" bind:value={selectedClassroom}>
				{#each classroomOptions as option}
					<option value={option.value}>{option.label}</option>
				{/each}
			</select>
			<select class="rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none" bind:value={selectedAssignment}>
				{#each assignmentOptions as option}
					<option value={option.value}>{option.label}</option>
				{/each}
			</select>
			<div class="flex items-center rounded-2xl border border-gray-200 px-4 py-3 text-sm text-gray-600">
				{$i18n.t('Results')}: {filteredItems.length}
			</div>
			<select class="rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none" bind:value={sortBy}>
				<option value="submitted_at">{$i18n.t('Sort by Latest')}</option>
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
				{$i18n.t('Loading review queue...')}
			</div>
		{:else if filteredItems.length === 0}
			<div class="rounded-3xl border border-gray-200 bg-white p-6 text-sm text-gray-500">
				{$i18n.t('No submissions match the current filters.')}
			</div>
		{:else}
			<div class="grid gap-4">
				{#each filteredItems as item}
					<div class="rounded-3xl border border-gray-200 bg-white p-5">
						<div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
							<div>
								<div class="text-lg font-semibold text-gray-900">{item.student_name}</div>
								<div class="mt-1 text-sm text-gray-500">{item.assignment.title}</div>
								<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
									<div>
										{$i18n.t('Classroom')}:
										{item.classroom ? getClassroomDisplayName(item.classroom.name) : t('Unknown')}
									</div>
									<div>{$i18n.t('Status')}: {getReviewStatusLabel(item.review_status)}</div>
									<div>{new Date(item.submission.submitted_at * 1000).toLocaleString()}</div>
								</div>
								<div class="mt-3 flex flex-wrap gap-2 text-xs">
									<div class="rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-gray-700">
										{$i18n.t('AI inserted')}: {item.analysis_summary?.ai_inserted_chars ?? 0}
									</div>
									<div class="rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-sky-700">
										{$i18n.t('AI pasted')}: {item.analysis_summary?.ai_pasted_chars ?? 0}
									</div>
									<div
										class={`rounded-full border px-3 py-1.5 ${
											getRiskTone(item) === 'rose'
												? 'border-rose-200 bg-rose-50 text-rose-700'
												: getRiskTone(item) === 'amber'
													? 'border-amber-200 bg-amber-50 text-amber-700'
													: 'border-gray-200 bg-gray-50 text-gray-700'
										}`}
									>
										{$i18n.t('Suspected Unmarked Imports')}: {item.analysis_summary?.suspected_unmarked_import_count ?? 0}
									</div>
									<div class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-amber-700">
										{$i18n.t('Large Bursts')}: {item.analysis_summary?.burst_count ?? 0}
									</div>
									<div class="rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-gray-700">
										{$i18n.t('Average Rewrite Ratio')}: {item.analysis_summary?.average_rewrite_ratio ?? 0}%
									</div>
								</div>
							</div>

							<div class="flex flex-wrap gap-2">
								<button
									class="rounded-full border border-gray-300 px-3 py-2 text-sm"
									on:click={() => goto(`/teacher/assignments/${item.assignment.id}`)}
								>
									{$i18n.t('Assignment')}
								</button>
								<button
									class="rounded-full bg-black px-3 py-2 text-sm text-white"
									on:click={() => goto(`/teacher/submissions/${item.submission.id}`)}
								>
									{$i18n.t('Open')}
								</button>
							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</TeacherPageShell>
