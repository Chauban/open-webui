<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';
	import dayjs from '$lib/dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';

	import { getTeacherAssignment } from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import EduActionMenu from '$lib/components/education/EduActionMenu.svelte';
	import EduBadge from '$lib/components/education/EduBadge.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduStatCard from '$lib/components/education/EduStatCard.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import { assignmentTabs } from '$lib/components/education/teacher-nav';
	import {
		formatEpoch,
		getAssignmentStatusLabel,
		getClassroomDisplayName,
		resolveErrorMessage
	} from '$lib/utils/education';

	// 作业首页此前是一整张编辑表单,老师点「打开作业」多半是想看进度。
	// 现在首页只答「交得怎么样、还要做什么」,编辑挪到「设置」标签。

	dayjs.extend(relativeTime);

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	const COACHING_TITLES = { socratic: 'Socratic', balanced: 'Balanced', hands_off: 'Hands-off' };
	const assignmentId = $page.params.assignmentId;

	let item = null;
	let loading = true;
	let loadError = '';

	$: assignment = item?.assignment;
	$: isPastDue =
		assignment?.status === 'active' && assignment?.due_at && assignment.due_at * 1000 < Date.now();
	$: unsubmittedCount = Math.max((item?.student_count ?? 0) - (item?.submission_count ?? 0), 0);
	$: base = `/teacher/assignments/${assignmentId}`;
	$: progressSegments = item
		? [
				{ key: 'reviewed', count: item.reviewed_count, className: 'bg-emerald-500' },
				{ key: 'returned', count: item.returned_count, className: 'bg-sky-400' },
				{ key: 'pending', count: item.pending_review_count, className: 'bg-amber-400' },
				{ key: 'unsubmitted', count: unsubmittedCount, className: 'bg-gray-200 dark:bg-gray-700' }
			]
		: [];

	const copyWriteLink = async () => {
		const link = `${window.location.origin}/assignments/${assignmentId}/write`;
		try {
			await navigator.clipboard.writeText(link);
			toast.success(t('Write link copied.'));
		} catch {
			toast.error(t('Failed to copy write link.'));
		}
	};

	onMount(async () => {
		try {
			item = await getTeacherAssignment(localStorage.token, assignmentId);
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
	title={assignment?.title ?? ''}
	tabs={assignmentTabs(assignmentId)}
>
	<svelte:fragment slot="nav-actions">
		{#if item}
			<EduButton size="sm" on:click={copyWriteLink}>{$i18n.t('Copy Student Link')}</EduButton>
			<EduActionMenu
				items={[
					{
						label: 'Duplicate as New Assignment',
						onClick: () => goto(`/teacher/assignments/new?from=${assignmentId}`)
					}
				]}
			/>
		{/if}
	</svelte:fragment>

	<div class="mx-auto max-w-6xl px-4 py-6">
		{#if loading}
			<EduStateCard>{$i18n.t('Loading assignment...')}</EduStateCard>
		{:else if loadError}
			<EduStateCard tone="error">{loadError}</EduStateCard>
		{:else}
			<div class="mb-5 flex flex-wrap items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
				{#if item.classroom}
					<a href={`/teacher/classrooms/${item.classroom.id}`} class="hover:underline">
						{getClassroomDisplayName(item.classroom.name, t)}
					</a>
					<span class="text-gray-300 dark:text-gray-600">·</span>
				{/if}
				<span title={formatEpoch(assignment.due_at)}>
					{$i18n.t('Due At')}: {formatEpoch(assignment.due_at)}
					<span class={isPastDue ? 'text-rose-600 dark:text-rose-400' : 'text-gray-400'}>
						({dayjs(assignment.due_at * 1000)
							.locale($i18n.language)
							.fromNow()})
					</span>
				</span>
				<EduBadge soft tone={assignment.status === 'archived' ? 'gray' : isPastDue ? 'rose' : 'emerald'}>
					{isPastDue ? $i18n.t('Past Due') : getAssignmentStatusLabel(assignment.status, t)}
				</EduBadge>
			</div>

			<div class="mb-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
				<EduStatCard
					label="Submitted"
					value={`${item.submission_count}/${item.student_count}`}
					hint="Students who handed in the current round"
					href={`${base}/submissions?status=all`}
				/>
				<EduStatCard
					label="To Review"
					value={item.pending_review_count}
					tone={item.pending_review_count > 0 ? 'amber' : 'default'}
					href={`${base}/submissions?status=pending`}
				/>
				<EduStatCard
					label="Returned"
					value={item.returned_count}
					hint="Waiting for the student to resubmit"
					href={`${base}/submissions?status=returned`}
				/>
				<EduStatCard
					label="Unsubmitted"
					value={unsubmittedCount}
					hint="Remind them or grant an extension"
					href={`${base}/submissions?status=unsubmitted`}
				/>
			</div>

			{#if item.student_count > 0}
				<EduCard class="mb-6">
					<div class="flex h-2.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
						{#each progressSegments as segment}
							{#if segment.count > 0}
								<div
									class={segment.className}
									style={`width: ${(segment.count / item.student_count) * 100}%`}
								></div>
							{/if}
						{/each}
					</div>
					<div class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
						<span><span class="mr-1 inline-block size-2 rounded-full bg-emerald-500"></span>{$i18n.t('Reviewed')} {item.reviewed_count}</span>
						<span><span class="mr-1 inline-block size-2 rounded-full bg-sky-400"></span>{$i18n.t('Returned')} {item.returned_count}</span>
						<span><span class="mr-1 inline-block size-2 rounded-full bg-amber-400"></span>{$i18n.t('To Review')} {item.pending_review_count}</span>
						<span><span class="mr-1 inline-block size-2 rounded-full bg-gray-300 dark:bg-gray-600"></span>{$i18n.t('Unsubmitted')} {unsubmittedCount}</span>
					</div>
				</EduCard>
			{/if}

			<EduCard>
				<div class="mb-4 flex items-center justify-between">
					<h2 class="text-sm font-semibold">{$i18n.t('Assignment Brief')}</h2>
					<EduButton variant="link" on:click={() => goto(`${base}/settings`)}>
						{$i18n.t('Edit settings')}
					</EduButton>
				</div>
				<div class="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300">
					{assignment.description || $i18n.t('No description')}
				</div>
				<dl class="mt-5 grid gap-x-6 gap-y-3 border-t border-gray-100 pt-4 text-sm sm:grid-cols-2 dark:border-gray-800">
					<div>
						<dt class="text-xs text-gray-500 dark:text-gray-400">{$i18n.t('Rubric')}</dt>
						<dd class="mt-0.5">
							{assignment.rubric_schema.criteria
								.map((criterion) => `${criterion.label} ${criterion.max_score}`)
								.join(' · ')}
							<span class="text-gray-400">/ {assignment.score_max}</span>
						</dd>
					</div>
					<div>
						<dt class="text-xs text-gray-500 dark:text-gray-400">{$i18n.t('AI Coaching Style')}</dt>
						<dd class="mt-0.5">{$i18n.t(COACHING_TITLES[assignment.coaching_style])}</dd>
					</div>
					<div>
						<dt class="text-xs text-gray-500 dark:text-gray-400">
							{$i18n.t('AI Reader Check Before Submitting')}
						</dt>
						<dd class="mt-0.5">
							{assignment.challenge_enabled
								? $i18n.t('AI reader check on · {{count}} rounds', {
										count: assignment.challenge_rounds
									})
								: $i18n.t('AI reader check off')}
						</dd>
					</div>
					<div>
						<dt class="text-xs text-gray-500 dark:text-gray-400">
							{$i18n.t('Reflection Before Submitting')}
						</dt>
						<dd class="mt-0.5">
							{$i18n.t('{{count}} reflection questions, plus "Did you use AI?"', {
								count: assignment.reflection_questions?.length ?? 0
							})}
						</dd>
					</div>
				</dl>
			</EduCard>
		{/if}
	</div>
</TeacherPageShell>
