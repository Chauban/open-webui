<script lang="ts">
	// @ts-nocheck
	import { getContext, onDestroy, onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import dayjs from 'dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';

	import { getTeacherOverview } from '$lib/apis/education';
	import { educationNotificationSummary } from '$lib/stores';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';

	dayjs.extend(relativeTime);

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	const DAY_MS = 24 * 60 * 60 * 1000;

	let overview = null;
	let loading = true;
	let loadError = '';
	let unsubscribeNotifications;
	let notificationsInitialized = false;

	const getClassroomDisplayName = (name: string) =>
		name?.trim() === 'Default Classroom' ? t('Default Classroom') : name;

	const formatRelative = (timestamp: number) => dayjs(timestamp * 1000).fromNow();
	const formatAbsolute = (timestamp: number) => new Date(timestamp * 1000).toLocaleString();

	const loadOverview = async () => {
		try {
			overview = await getTeacherOverview(localStorage.token);
			loadError = '';
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		} finally {
			loading = false;
		}
	};

	onMount(async () => {
		await loadOverview();
		// 与学生端首页同一模式:收到教学通知(store 刷新)时后台重拉;跳过订阅触发的初始值
		unsubscribeNotifications = educationNotificationSummary.subscribe(() => {
			if (!notificationsInitialized) {
				notificationsInitialized = true;
				return;
			}
			loadOverview();
		});
	});

	onDestroy(() => {
		unsubscribeNotifications?.();
	});
</script>

<TeacherPageShell title="Overview">
	<div class="mx-auto max-w-6xl px-4 py-8">
		<div class="mb-8 text-sm text-gray-500">
			{$i18n.t('Track classroom activity, assignments, and recent submissions from one place.')}
		</div>

		<TeacherSectionNav />

		{#if loadError}
			<div class="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
				{loadError}
			</div>
		{:else if loading}
			<div class="rounded-3xl border border-gray-200 bg-white p-6 text-sm text-gray-500">
				{$i18n.t('Loading teaching overview...')}
			</div>
		{:else}
			<div class="mb-8 grid gap-4 md:grid-cols-4">
				<div class="rounded-3xl border border-gray-200 bg-white p-5">
					<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('Classrooms')}</div>
					<div class="mt-2 text-3xl font-semibold">{overview.classroom_count}</div>
				</div>
				<div class="rounded-3xl border border-gray-200 bg-white p-5">
					<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('Assignments')}</div>
					<div class="mt-2 text-3xl font-semibold">{overview.assignment_count}</div>
				</div>
				<div class="rounded-3xl border border-gray-200 bg-white p-5">
					<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('To Review')}</div>
					<div class="mt-2 text-3xl font-semibold">{overview.pending_review_count}</div>
				</div>
				<div class="rounded-3xl border border-gray-200 bg-white p-5">
					<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('Unsubmitted')}</div>
					<div class="mt-2 text-3xl font-semibold">{overview.unsubmitted_count}</div>
				</div>
			</div>

			<div class="mb-8 grid gap-4 lg:grid-cols-[1.05fr_0.95fr]">
				<div class="rounded-3xl border border-gray-200 bg-white p-5">
					<div class="mb-4 flex items-center justify-between">
						<div class="text-sm font-semibold">{$i18n.t('To Review')}</div>
						<button class="text-sm text-gray-500" on:click={() => goto('/teacher/review')}>
							{$i18n.t('Open review queue')}
						</button>
					</div>
					{#if overview.pending_review_items.length === 0}
						<div
							class="rounded-2xl border border-dashed border-gray-300 px-4 py-5 text-sm text-gray-500"
						>
							{$i18n.t('No submissions to review yet.')}
						</div>
					{:else}
						<div class="space-y-3">
							{#each overview.pending_review_items as item}
								<button
									class="w-full rounded-2xl border border-gray-200 px-4 py-4 text-left text-sm transition hover:border-gray-300"
									on:click={() => goto(`/teacher/submissions/${item.submission.id}`)}
								>
									<div class="font-medium text-gray-900">{item.student_name}</div>
									<div class="mt-1 text-gray-500">{item.assignment.title}</div>
									<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
										<div>{item.classroom ? getClassroomDisplayName(item.classroom.name) : t('Unknown')}</div>
										<div title={formatAbsolute(item.submission.submitted_at)}>
											{formatRelative(item.submission.submitted_at)}
										</div>
									</div>
									<div class="mt-3 flex flex-wrap gap-2 text-xs">
										<div class="rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-rose-700">
											{$i18n.t('Suspected Unmarked Imports')}: {item.analysis_summary?.suspected_unmarked_import_count ?? 0}
										</div>
										<div class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-700">
											{$i18n.t('Large Bursts')}: {item.analysis_summary?.burst_count ?? 0}
										</div>
									</div>
								</button>
							{/each}
						</div>
					{/if}
				</div>

				<div class="rounded-3xl border border-gray-200 bg-white p-5">
					<div class="mb-4 flex items-center justify-between">
						<div class="text-sm font-semibold">{$i18n.t('Recent Submissions')}</div>
						<button class="text-sm text-gray-500" on:click={() => goto('/teacher/assignments')}>
							{$i18n.t('Open assignments')}
						</button>
					</div>
					{#if overview.recent_submissions.length === 0}
						<div
							class="rounded-2xl border border-dashed border-gray-300 px-4 py-5 text-sm text-gray-500"
						>
							{$i18n.t('No submissions yet.')}
						</div>
					{:else}
						<div class="space-y-3">
							{#each overview.recent_submissions as item}
								<button
									class="w-full rounded-2xl border border-gray-200 px-4 py-4 text-left text-sm transition hover:border-gray-300"
									on:click={() => goto(`/teacher/submissions/${item.submission.id}`)}
								>
									<div class="font-medium text-gray-900">{item.student_name}</div>
									<div class="mt-1 text-gray-500">{item.assignment.title}</div>
									<div class="mt-3 text-xs text-gray-500" title={formatAbsolute(item.submission.submitted_at)}>
										{formatRelative(item.submission.submitted_at)}
									</div>
									<div class="mt-3 flex flex-wrap gap-2 text-xs">
										<div class="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-sky-700">
											{$i18n.t('AI pasted')}: {item.analysis_summary?.ai_pasted_chars ?? 0}
										</div>
										<div class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-700">
											{$i18n.t('Large Bursts')}: {item.analysis_summary?.burst_count ?? 0}
										</div>
									</div>
								</button>
							{/each}
						</div>
					{/if}
				</div>
			</div>

			<div class="mb-8 rounded-3xl border border-gray-200 bg-white p-5">
				<div class="mb-4 flex items-center justify-between">
					<div class="text-sm font-semibold">{$i18n.t('Upcoming Due')}</div>
					<button class="text-sm text-gray-500" on:click={() => goto('/teacher/assignments')}>
						{$i18n.t('View all')}
					</button>
				</div>
				{#if (overview.upcoming_due_assignments ?? []).length === 0}
					<div class="rounded-2xl border border-dashed border-gray-300 px-4 py-5 text-sm text-gray-500">
						{$i18n.t('No upcoming due assignments.')}
					</div>
				{:else}
					<div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
						{#each overview.upcoming_due_assignments as item}
							<button
								class="rounded-2xl border border-gray-200 px-4 py-4 text-left text-sm transition hover:border-gray-300"
								on:click={() => goto(`/teacher/assignments/${item.assignment.id}`)}
							>
								<div class="font-medium text-gray-900">{item.assignment.title}</div>
								<div class="mt-1 text-gray-500">
									{item.classroom ? getClassroomDisplayName(item.classroom.name) : t('Unassigned classroom')}
								</div>
								<div class="mt-3 flex flex-wrap items-center gap-2 text-xs">
									<div
										class={`rounded-full border px-3 py-1 ${
											item.assignment.due_at * 1000 - Date.now() < DAY_MS
												? 'border-amber-200 bg-amber-50 text-amber-700'
												: 'border-gray-200 bg-gray-50 text-gray-600'
										}`}
										title={formatAbsolute(item.assignment.due_at)}
									>
										{$i18n.t('Due')} {formatRelative(item.assignment.due_at)}
									</div>
									<div class="text-gray-500">
										{$i18n.t('Submissions')}: {item.submission_count}/{item.student_count}
									</div>
								</div>
							</button>
						{/each}
					</div>
				{/if}
			</div>

			<div class="mb-8 rounded-3xl border border-gray-200 bg-white p-5">
				<div class="mb-4 flex items-center justify-between">
					<div class="text-sm font-semibold">{$i18n.t('Recent Assignments')}</div>
					<button class="text-sm text-gray-500" on:click={() => goto('/teacher/assignments')}>
						{$i18n.t('View all')}
					</button>
				</div>
				{#if overview.recent_assignments.length === 0}
					<div class="rounded-2xl border border-dashed border-gray-300 px-4 py-5 text-sm text-gray-500">
						{$i18n.t('No assignments yet.')}
					</div>
				{:else}
					<div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
						{#each overview.recent_assignments as item}
							<button
								class="rounded-2xl border border-gray-200 px-4 py-4 text-left text-sm transition hover:border-gray-300"
								on:click={() => goto(`/teacher/assignments/${item.assignment.id}`)}
							>
								<div class="font-medium text-gray-900">{item.assignment.title}</div>
								<div class="mt-1 text-gray-500">
									{item.classroom ? getClassroomDisplayName(item.classroom.name) : t('Unassigned classroom')}
								</div>
								<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
									<div>{$i18n.t('Students')}: {item.student_count}</div>
									<div>{$i18n.t('Submissions')}: {item.submission_count}</div>
								</div>
								<div class="mt-3 flex flex-wrap gap-2 text-xs">
									<div class="rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-rose-700">
										{$i18n.t('Suspected Unmarked Imports')}: {item.risk_summary?.suspected_unmarked_import_count ?? 0}
									</div>
									<div class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-700">
										{$i18n.t('Large Bursts')}: {item.risk_summary?.burst_count ?? 0}
									</div>
								</div>
							</button>
						{/each}
					</div>
				{/if}
			</div>

			<div class="rounded-3xl border border-gray-200 bg-white p-5">
				<div class="mb-4 flex items-center justify-between">
					<div class="text-sm font-semibold">{$i18n.t('Classrooms')}</div>
					<button class="text-sm text-gray-500" on:click={() => goto('/teacher/classrooms')}>
						{$i18n.t('View all')}
					</button>
				</div>
				{#if overview.classrooms.length === 0}
					<div class="rounded-2xl border border-dashed border-gray-300 px-4 py-5 text-sm text-gray-500">
						{$i18n.t('No classrooms yet.')}
					</div>
				{:else}
					<div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
						{#each overview.classrooms as item}
							<button
								class="rounded-2xl border border-gray-200 px-4 py-4 text-left text-sm transition hover:border-gray-300"
								on:click={() => goto(`/teacher/classrooms/${item.classroom.id}`)}
							>
								<div class="font-medium text-gray-900">
									{getClassroomDisplayName(item.classroom.name)}
								</div>
								<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
									<div>{$i18n.t('Students')}: {item.student_count}</div>
									<div>{$i18n.t('Assignments')}: {item.assignment_count}</div>
								</div>
								<div class="mt-3 flex flex-wrap gap-2 text-xs">
									<div class="rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-rose-700">
										{$i18n.t('Suspected Unmarked Imports')}: {item.risk_summary?.suspected_unmarked_import_count ?? 0}
									</div>
									<div class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-700">
										{$i18n.t('Large Bursts')}: {item.risk_summary?.burst_count ?? 0}
									</div>
								</div>
							</button>
						{/each}
					</div>
				{/if}
			</div>
		{/if}
	</div>
</TeacherPageShell>
