<script lang="ts">
	// @ts-nocheck
	import { getContext, onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';
	import dayjs from 'dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';

	import {
		getTeacherAssignments,
		getTeacherClassrooms,
		getTeacherReview,
		getEducationNotificationSummary,
		markEducationNotificationsRead
	} from '$lib/apis/education';
	import { educationNotificationSummary } from '$lib/stores';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';
	import { getClassroomDisplayName, getReviewStatusLabel } from '$lib/utils/education';

	dayjs.extend(relativeTime);

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	const getRiskTone = (item) => {
		if ((item.risk_summary?.suspected_unmarked_import_count ?? 0) > 0) return 'rose';
		if ((item.risk_summary?.burst_count ?? 0) > 0) return 'amber';
		return 'gray';
	};

	const PAGE_SIZE = 50;

	let items = [];
	let total = 0;
	let loading = true;
	let loadingMore = false;
	let loadError = '';
	let selectedStatus = 'pending';
	let selectedClassroom = 'all';
	let selectedAssignment = 'all';
	let onlySuspected = false;
	let onlyBursts = false;
	let sortBy = 'latest';
	let classrooms = [];
	let assignments = [];
	let unsubscribeNotifications;
	let notificationsInitialized = false;
	let loadSeq = 0;

	$: classroomOptions = [
		{ value: 'all', label: t('All Classrooms') },
		...classrooms.map((item) => ({
			value: item.classroom.id,
			label: getClassroomDisplayName(item.classroom.name, t)
		}))
	];

	$: assignmentOptions = [
		{ value: 'all', label: t('All Assignments') },
		...assignments.map((item) => ({
			value: item.assignment.id,
			label: item.assignment.title
		}))
	];

	const buildQueryParams = (offset: number) => ({
		review_status: selectedStatus === 'all' ? undefined : selectedStatus,
		classroom_id: selectedClassroom === 'all' ? undefined : selectedClassroom,
		assignment_id: selectedAssignment === 'all' ? undefined : selectedAssignment,
		sort: sortBy,
		only_suspected: onlySuspected ? true : undefined,
		only_bursts: onlyBursts ? true : undefined,
		limit: PAGE_SIZE,
		offset
	});

	const loadQueue = async () => {
		const seq = ++loadSeq;
		loading = true;
		try {
			const res = await getTeacherReview(localStorage.token, buildQueryParams(0));
			if (seq !== loadSeq) return;
			items = res.items ?? [];
			total = res.total ?? items.length;
			loadError = '';
		} catch (error) {
			if (seq !== loadSeq) return;
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		} finally {
			if (seq === loadSeq) {
				loading = false;
			}
		}
	};

	const loadMore = async () => {
		const seq = loadSeq;
		loadingMore = true;
		try {
			const res = await getTeacherReview(localStorage.token, buildQueryParams(items.length));
			if (seq !== loadSeq) return;
			items = [...items, ...(res.items ?? [])];
			total = res.total ?? total;
		} catch (error) {
			if (seq !== loadSeq) return;
			toast.error(`${error?.detail ?? error}`);
		} finally {
			if (seq === loadSeq) {
				loadingMore = false;
			}
		}
	};

	const selectStatus = (value: string) => {
		if (selectedStatus === value) return;
		selectedStatus = value;
		loadQueue();
	};

	const clearSubmissionNotifications = async () => {
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
	};

	onMount(async () => {
		await loadQueue();

		getTeacherClassrooms(localStorage.token)
			.then((res) => (classrooms = res ?? []))
			.catch(() => {});
		getTeacherAssignments(localStorage.token)
			.then((res) => (assignments = res ?? []))
			.catch(() => {});

		await clearSubmissionNotifications();

		// 新提交通知到达时自动刷新队列;summary 无未读提交时跳过,避免 mark-read 回写触发循环
		unsubscribeNotifications = educationNotificationSummary.subscribe((summary) => {
			if (!notificationsInitialized) {
				notificationsInitialized = true;
				return;
			}
			if ((summary?.by_type?.submission_created ?? 0) === 0) {
				return;
			}
			loadQueue();
			clearSubmissionNotifications();
		});
	});

	onDestroy(() => {
		unsubscribeNotifications?.();
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
				on:click={() => selectStatus('pending')}
			>
				{$i18n.t('To Review')}
			</button>
			<button
				class={`rounded-full border px-4 py-2 text-sm transition ${
					selectedStatus === 'reviewed'
						? 'border-black bg-black text-white'
						: 'border-gray-300 bg-white text-gray-700'
				}`}
				on:click={() => selectStatus('reviewed')}
			>
				{$i18n.t('Reviewed')}
			</button>
			<button
				class={`rounded-full border px-4 py-2 text-sm transition ${
					selectedStatus === 'returned'
						? 'border-black bg-black text-white'
						: 'border-gray-300 bg-white text-gray-700'
				}`}
				on:click={() => selectStatus('returned')}
			>
				{$i18n.t('Returned')}
			</button>
			<button
				class={`rounded-full border px-4 py-2 text-sm transition ${
					selectedStatus === 'all'
						? 'border-black bg-black text-white'
						: 'border-gray-300 bg-white text-gray-700'
				}`}
				on:click={() => selectStatus('all')}
			>
				{$i18n.t('All')}
			</button>
		</div>

		<div class="mb-8 grid gap-3 rounded-3xl border border-gray-200 bg-white p-5 md:grid-cols-4">
			<select class="rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none" bind:value={selectedClassroom} on:change={() => loadQueue()}>
				{#each classroomOptions as option}
					<option value={option.value}>{option.label}</option>
				{/each}
			</select>
			<select class="rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none" bind:value={selectedAssignment} on:change={() => loadQueue()}>
				{#each assignmentOptions as option}
					<option value={option.value}>{option.label}</option>
				{/each}
			</select>
			<div class="flex items-center rounded-2xl border border-gray-200 px-4 py-3 text-sm text-gray-600">
				{$i18n.t('Results')}: {items.length} / {total}
			</div>
			<select class="rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none" bind:value={sortBy} on:change={() => loadQueue()}>
				<option value="latest">{$i18n.t('Sort by Latest')}</option>
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
				on:click={() => { onlySuspected = !onlySuspected; loadQueue(); }}
			>
				{$i18n.t('Only Suspected Imports')}
			</button>
			<button
				class={`rounded-full border px-4 py-2 text-sm transition ${
					onlyBursts ? 'border-amber-300 bg-amber-50 text-amber-700' : 'border-gray-300 bg-white text-gray-700'
				}`}
				on:click={() => { onlyBursts = !onlyBursts; loadQueue(); }}
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
		{:else if items.length === 0}
			<div class="rounded-3xl border border-gray-200 bg-white p-6 text-sm text-gray-500">
				{$i18n.t('No submissions match the current filters.')}
			</div>
		{:else}
			<div class="grid gap-4">
				{#each items as item}
					<div class="rounded-3xl border border-gray-200 bg-white p-5">
						<div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
							<div>
								<div class="text-lg font-semibold text-gray-900">{item.student_name}</div>
								<div class="mt-1 text-sm text-gray-500">{item.assignment.title}</div>
								<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
									<div>
										{$i18n.t('Classroom')}:
										{item.classroom ? getClassroomDisplayName(item.classroom.name, t) : t('Unknown')}
									</div>
									<div>{$i18n.t('Status')}: {getReviewStatusLabel(item.review_status, t)}</div>
									<div title={new Date(item.submission.submitted_at * 1000).toLocaleString()}>
										{dayjs(item.submission.submitted_at * 1000).fromNow()}
									</div>
								</div>
								<div class="mt-3 flex flex-wrap gap-2 text-xs">
									<div class="rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-gray-700">
										{$i18n.t('AI inserted')}: {item.risk_summary?.ai_inserted_chars ?? 0}
									</div>
									<div class="rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-sky-700">
										{$i18n.t('AI pasted')}: {item.risk_summary?.ai_pasted_chars ?? 0}
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
										{$i18n.t('Suspected Unmarked Imports')}: {item.risk_summary?.suspected_unmarked_import_count ?? 0}
									</div>
									<div class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-amber-700">
										{$i18n.t('Large Bursts')}: {item.risk_summary?.burst_count ?? 0}
									</div>
									<div class="rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-gray-700">
										{$i18n.t('Average Rewrite Ratio')}: {item.risk_summary?.average_rewrite_ratio ?? 0}%
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

			{#if items.length < total}
				<div class="mt-6 flex justify-center">
					<button
						class="rounded-full border border-gray-300 bg-white px-6 py-2.5 text-sm text-gray-700 transition hover:border-gray-400 disabled:opacity-60"
						disabled={loadingMore}
						on:click={loadMore}
					>
						{loadingMore ? $i18n.t('Loading...') : $i18n.t('Load More')}
						({items.length}/{total})
					</button>
				</div>
			{/if}
		{/if}
	</div>
</TeacherPageShell>
