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
	import EduBadge from '$lib/components/education/EduBadge.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduEmpty from '$lib/components/education/EduEmpty.svelte';
	import EduStatCard from '$lib/components/education/EduStatCard.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import EduTile from '$lib/components/education/EduTile.svelte';
	import { getClassroomDisplayName } from '$lib/utils/education';

	dayjs.extend(relativeTime);

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	const DAY_MS = 24 * 60 * 60 * 1000;

	let overview = null;
	let loading = true;
	let loadError = '';
	let unsubscribeNotifications;
	let notificationsInitialized = false;


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
			<EduStateCard tone="error">{loadError}</EduStateCard>
		{:else if loading}
			<EduStateCard>{$i18n.t('Loading teaching overview...')}</EduStateCard>
		{:else}
			<div class="mb-8 grid gap-4 md:grid-cols-4">
				<EduStatCard label="Classrooms" value={overview.classroom_count} />
				<EduStatCard label="Assignments" value={overview.assignment_count} />
				<EduStatCard label="To Review" value={overview.pending_review_count} />
				<EduStatCard label="Unsubmitted" value={overview.unsubmitted_count} />
			</div>

			<div class="mb-8 grid gap-4 lg:grid-cols-[1.05fr_0.95fr]">
				<EduCard>
					<div class="mb-4 flex items-center justify-between">
						<div class="text-sm font-semibold">{$i18n.t('To Review')}</div>
						<EduButton variant="link" on:click={() => goto('/teacher/review')}>
							{$i18n.t('Open review queue')}
						</EduButton>
					</div>
					{#if overview.pending_review_items.length === 0}
						<EduEmpty>{$i18n.t('No submissions to review yet.')}</EduEmpty>
					{:else}
						<div class="space-y-3">
							{#each overview.pending_review_items as item}
								<EduTile
									interactive
									on:click={() => goto(`/teacher/submissions/${item.submission.id}`)}
								>
									<div class="font-medium text-gray-900">{item.student_name}</div>
									<div class="mt-1 text-gray-500">{item.assignment.title}</div>
									<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
										<div>{item.classroom ? getClassroomDisplayName(item.classroom.name, t) : t('Unknown')}</div>
										<div title={formatAbsolute(item.submission.submitted_at)}>
											{formatRelative(item.submission.submitted_at)}
										</div>
									</div>
									<div class="mt-3 flex flex-wrap gap-2 text-xs">
										<EduBadge tone="rose">
											{$i18n.t('Suspected Unmarked Imports')}: {item.risk_summary
												?.suspected_unmarked_import_count ?? 0}
										</EduBadge>
										<EduBadge tone="amber">
											{$i18n.t('Large Bursts')}: {item.risk_summary?.burst_count ?? 0}
										</EduBadge>
									</div>
								</EduTile>
							{/each}
						</div>
					{/if}
				</EduCard>

				<EduCard>
					<div class="mb-4 flex items-center justify-between">
						<div class="text-sm font-semibold">{$i18n.t('Recent Submissions')}</div>
						<EduButton variant="link" on:click={() => goto('/teacher/assignments')}>
							{$i18n.t('Open assignments')}
						</EduButton>
					</div>
					{#if overview.recent_submissions.length === 0}
						<EduEmpty>{$i18n.t('No submissions yet.')}</EduEmpty>
					{:else}
						<div class="space-y-3">
							{#each overview.recent_submissions as item}
								<EduTile
									interactive
									on:click={() => goto(`/teacher/submissions/${item.submission.id}`)}
								>
									<div class="font-medium text-gray-900">{item.student_name}</div>
									<div class="mt-1 text-gray-500">{item.assignment.title}</div>
									<div class="mt-3 text-xs text-gray-500" title={formatAbsolute(item.submission.submitted_at)}>
										{formatRelative(item.submission.submitted_at)}
									</div>
									<div class="mt-3 flex flex-wrap gap-2 text-xs">
										<EduBadge tone="sky">
											{$i18n.t('AI pasted')}: {item.risk_summary?.ai_pasted_chars ?? 0}
										</EduBadge>
										<EduBadge tone="amber">
											{$i18n.t('Large Bursts')}: {item.risk_summary?.burst_count ?? 0}
										</EduBadge>
									</div>
								</EduTile>
							{/each}
						</div>
					{/if}
				</EduCard>
			</div>

			<EduCard class="mb-8">
				<div class="mb-4 flex items-center justify-between">
					<div class="text-sm font-semibold">{$i18n.t('Upcoming Due')}</div>
					<EduButton variant="link" on:click={() => goto('/teacher/assignments')}>
						{$i18n.t('View all')}
					</EduButton>
				</div>
				{#if (overview.upcoming_due_assignments ?? []).length === 0}
					<EduEmpty>{$i18n.t('No upcoming due assignments.')}</EduEmpty>
				{:else}
					<div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
						{#each overview.upcoming_due_assignments as item}
							<EduTile
								interactive
								on:click={() => goto(`/teacher/assignments/${item.assignment.id}`)}
							>
								<div class="font-medium text-gray-900">{item.assignment.title}</div>
								<div class="mt-1 text-gray-500">
									{item.classroom ? getClassroomDisplayName(item.classroom.name, t) : t('Unassigned classroom')}
								</div>
								<div class="mt-3 flex flex-wrap items-center gap-2 text-xs">
									<EduBadge
										tone={item.assignment.due_at * 1000 - Date.now() < DAY_MS ? 'amber' : 'gray'}
										title={formatAbsolute(item.assignment.due_at)}
									>
										{$i18n.t('Due')} {formatRelative(item.assignment.due_at)}
									</EduBadge>
									<div class="text-gray-500">
										{$i18n.t('Submissions')}: {item.submission_count}/{item.student_count}
									</div>
								</div>
							</EduTile>
						{/each}
					</div>
				{/if}
			</EduCard>

			<EduCard class="mb-8">
				<div class="mb-4 flex items-center justify-between">
					<div class="text-sm font-semibold">{$i18n.t('Recent Assignments')}</div>
					<EduButton variant="link" on:click={() => goto('/teacher/assignments')}>
						{$i18n.t('View all')}
					</EduButton>
				</div>
				{#if overview.recent_assignments.length === 0}
					<EduEmpty>{$i18n.t('No assignments yet.')}</EduEmpty>
				{:else}
					<div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
						{#each overview.recent_assignments as item}
							<EduTile
								interactive
								on:click={() => goto(`/teacher/assignments/${item.assignment.id}`)}
							>
								<div class="font-medium text-gray-900">{item.assignment.title}</div>
								<div class="mt-1 text-gray-500">
									{item.classroom ? getClassroomDisplayName(item.classroom.name, t) : t('Unassigned classroom')}
								</div>
								<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
									<div>{$i18n.t('Students')}: {item.student_count}</div>
									<div>{$i18n.t('Submissions')}: {item.submission_count}</div>
								</div>
								<div class="mt-3 flex flex-wrap gap-2 text-xs">
									<EduBadge tone="rose">
										{$i18n.t('Suspected Unmarked Imports')}: {item.risk_summary
											?.suspected_unmarked_import_count ?? 0}
									</EduBadge>
									<EduBadge tone="amber">
										{$i18n.t('Large Bursts')}: {item.risk_summary?.burst_count ?? 0}
									</EduBadge>
								</div>
							</EduTile>
						{/each}
					</div>
				{/if}
			</EduCard>

			<EduCard>
				<div class="mb-4 flex items-center justify-between">
					<div class="text-sm font-semibold">{$i18n.t('Classrooms')}</div>
					<EduButton variant="link" on:click={() => goto('/teacher/classrooms')}>
						{$i18n.t('View all')}
					</EduButton>
				</div>
				{#if overview.classrooms.length === 0}
					<EduEmpty>{$i18n.t('No classrooms yet.')}</EduEmpty>
				{:else}
					<div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
						{#each overview.classrooms as item}
							<EduTile
								interactive
								on:click={() => goto(`/teacher/classrooms/${item.classroom.id}`)}
							>
								<div class="font-medium text-gray-900">
									{getClassroomDisplayName(item.classroom.name, t)}
								</div>
								<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
									<div>{$i18n.t('Students')}: {item.student_count}</div>
									<div>{$i18n.t('Assignments')}: {item.assignment_count}</div>
								</div>
								<div class="mt-3 flex flex-wrap gap-2 text-xs">
									<EduBadge tone="rose">
										{$i18n.t('Suspected Unmarked Imports')}: {item.risk_summary
											?.suspected_unmarked_import_count ?? 0}
									</EduBadge>
									<EduBadge tone="amber">
										{$i18n.t('Large Bursts')}: {item.risk_summary?.burst_count ?? 0}
									</EduBadge>
								</div>
							</EduTile>
						{/each}
					</div>
				{/if}
			</EduCard>
		{/if}
	</div>
</TeacherPageShell>
