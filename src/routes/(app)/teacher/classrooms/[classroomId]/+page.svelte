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

	import {
		exportClassroomProgress,
		getClassroomProgress,
		getTeacherClassroomAssignments,
		regenerateClassroomInviteCode
	} from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import EduActionMenu from '$lib/components/education/EduActionMenu.svelte';
	import EduBadge from '$lib/components/education/EduBadge.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduStatCard from '$lib/components/education/EduStatCard.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import { classroomTabs } from '$lib/components/education/teacher-nav';
	import {
		formatEpoch,
		getAssignmentStatusLabel,
		getClassroomDisplayName,
		resolveErrorMessage
	} from '$lib/utils/education';

	// 班级首页:此前 8 个统计数 + 3 张跳转卡 + 「作业进度」「最近作业」两份
	// 同一批作业的列表(前者还点不动)。现在是 4 个能点进去的数 + 一张作业表。
	// 邀请码只在建班初期是主角:还没学生时放大讲清楚,有学生后收成一行。

	dayjs.extend(relativeTime);

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	const classroomId = $page.params.classroomId;

	let classroom = null;
	let studentCount = 0;
	let assignments = [];
	let loading = true;
	let loadError = '';
	let showRegenerateConfirm = false;

	$: pendingCount = assignments.reduce((sum, item) => sum + item.pending_review_count, 0);
	$: returnedCount = assignments.reduce((sum, item) => sum + item.returned_count, 0);
	$: sortedAssignments = [...assignments].sort((a, b) => {
		const rank = (item) =>
			item.assignment.status !== 'active' ? 2 : item.assignment.due_at * 1000 >= Date.now() ? 0 : 1;
		return (
			rank(a) - rank(b) ||
			(rank(a) === 0
				? a.assignment.due_at - b.assignment.due_at
				: b.assignment.due_at - a.assignment.due_at)
		);
	});

	const isPastDue = (item) =>
		item.assignment.status === 'active' && item.assignment.due_at * 1000 < Date.now();

	const copyText = async (text: string, successMessage: string) => {
		try {
			await navigator.clipboard.writeText(text);
			toast.success(successMessage);
		} catch {
			toast.error(t('Failed to copy.'));
		}
	};

	const copyInviteCode = () => copyText(classroom.invite_code, t('Invite code copied.'));
	const copyInviteLink = () =>
		copyText(
			`${window.location.origin}/join?code=${encodeURIComponent(classroom.invite_code)}`,
			t('Invite link copied.')
		);

	const regenerateCode = async () => {
		try {
			const response = await regenerateClassroomInviteCode(localStorage.token, classroomId);
			classroom = response.classroom;
			toast.success(t('Invite code regenerated.'));
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		}
	};

	const downloadProgress = async () => {
		try {
			const csv = await exportClassroomProgress(localStorage.token, classroomId);
			const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
			const url = URL.createObjectURL(blob);
			const link = document.createElement('a');
			link.href = url;
			link.download = `${classroom?.name || 'classroom'}-progress.csv`;
			link.click();
			URL.revokeObjectURL(url);
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		}
	};

	onMount(async () => {
		try {
			const [progress, assignmentList] = await Promise.all([
				getClassroomProgress(localStorage.token, classroomId),
				getTeacherClassroomAssignments(localStorage.token, classroomId)
			]);
			classroom = progress.classroom;
			studentCount = progress.student_count;
			assignments = assignmentList ?? [];
		} catch (error) {
			loadError = resolveErrorMessage(error, t);
			toast.error(loadError);
		} finally {
			loading = false;
		}
	});
</script>

<TeacherPageShell
	crumbs={[{ label: $i18n.t('Classrooms'), href: '/teacher/classrooms' }]}
	title={classroom ? getClassroomDisplayName(classroom.name, t) : ''}
	tabs={classroomTabs(classroomId)}
>
	<svelte:fragment slot="nav-actions">
		{#if classroom}
			<EduButton
				variant="primary"
				size="sm"
				on:click={() => goto(`/teacher/assignments/new?classroomId=${classroomId}`)}
			>
				{$i18n.t('Create Assignment')}
			</EduButton>
			<EduActionMenu
				items={[
					{ label: 'Export Progress (CSV)', onClick: downloadProgress },
					{
						label: 'Regenerate Invite Code',
						danger: true,
						onClick: () => (showRegenerateConfirm = true)
					}
				]}
			/>
		{/if}
	</svelte:fragment>

	<div class="mx-auto max-w-6xl px-4 py-6">
		{#if loading}
			<EduStateCard>{$i18n.t('Loading classroom...')}</EduStateCard>
		{:else if loadError}
			<EduStateCard tone="error">{loadError}</EduStateCard>
		{:else}
			{#if studentCount === 0}
				<EduCard tone="sky" class="mb-6">
					<div class="text-sm font-semibold">{$i18n.t('Invite your students')}</div>
					<div class="mt-1 text-sm text-gray-600 dark:text-gray-300">
						{$i18n.t(
							'Students enter this code when they sign up or on the join page. You can also add them yourself under Students.'
						)}
					</div>
					<div class="mt-4 flex flex-wrap items-center gap-3">
						<div class="font-mono text-3xl font-semibold">{classroom.invite_code}</div>
						<EduButton size="sm" on:click={copyInviteCode}>{$i18n.t('Copy Code')}</EduButton>
						<EduButton size="sm" on:click={copyInviteLink}>{$i18n.t('Copy Invite Link')}</EduButton>
					</div>
				</EduCard>
			{:else}
				<div class="mb-5 flex flex-wrap items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
					<span class="text-gray-500 dark:text-gray-400">{$i18n.t('Invite Code')}</span>
					<button
						type="button"
						class="rounded-lg px-1.5 py-0.5 font-mono font-semibold transition hover:bg-gray-100 dark:hover:bg-gray-800"
						title={$i18n.t('Copy Code')}
						on:click={copyInviteCode}
					>
						{classroom.invite_code}
					</button>
					<EduButton variant="link" on:click={copyInviteLink}>{$i18n.t('Copy Invite Link')}</EduButton>
				</div>
			{/if}

			<div class="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
				<EduStatCard label="Students" value={studentCount} href={`/teacher/classrooms/${classroomId}/students`} />
				<EduStatCard label="Assignments" value={assignments.length} href={`/teacher/assignments?classroom=${classroomId}`} />
				<EduStatCard
					label="To Review"
					value={pendingCount}
					tone={pendingCount > 0 ? 'amber' : 'default'}
					href={`/teacher/review?status=pending&classroom=${classroomId}`}
				/>
				<EduStatCard
					label="Returned"
					value={returnedCount}
					hint="Waiting for the student to resubmit"
					href={`/teacher/review?status=returned&classroom=${classroomId}`}
				/>
			</div>

			<EduCard padding="none">
				<div class="flex items-center justify-between border-b border-gray-100 px-4 py-3 dark:border-gray-800">
					<h2 class="text-sm font-semibold">{$i18n.t('Assignments')}</h2>
				</div>
				{#if sortedAssignments.length === 0}
					<div class="px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
						{$i18n.t('No assignments yet.')}
					</div>
				{:else}
					<div class="overflow-x-auto">
						<table class="w-full min-w-[40rem] text-sm">
							<thead class="bg-gray-50 text-left text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400">
								<tr>
									<th class="px-4 py-2.5 font-medium">{$i18n.t('Assignment')}</th>
									<th class="px-4 py-2.5 font-medium">{$i18n.t('Due At')}</th>
									<th class="px-4 py-2.5 text-right font-medium">{$i18n.t('Submitted')}</th>
									<th class="px-4 py-2.5 text-right font-medium">{$i18n.t('To Review')}</th>
									<th class="px-4 py-2.5 text-right font-medium">{$i18n.t('Returned')}</th>
								</tr>
							</thead>
							<tbody>
								{#each sortedAssignments as item (item.assignment.id)}
									<tr
										class="cursor-pointer border-t border-gray-100 transition hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/60"
										on:click={() => goto(`/teacher/assignments/${item.assignment.id}`)}
									>
										<td class="px-4 py-3">
											<a
												href={`/teacher/assignments/${item.assignment.id}`}
												class="font-medium text-gray-900 hover:underline dark:text-gray-100"
												on:click|stopPropagation
											>
												{item.assignment.title}
											</a>
											{#if item.assignment.status === 'archived'}
												<EduBadge soft class="ml-1.5">{getAssignmentStatusLabel('archived', t)}</EduBadge>
											{/if}
										</td>
										<td class="whitespace-nowrap px-4 py-3" title={formatEpoch(item.assignment.due_at)}>
											<span class={isPastDue(item) ? 'text-rose-600 dark:text-rose-400' : ''}>
												{formatEpoch(item.assignment.due_at)}
											</span>
											<span class="ml-1 text-xs text-gray-400">
												{dayjs(item.assignment.due_at * 1000)
													.locale($i18n.language)
													.fromNow()}
											</span>
										</td>
										<td class="px-4 py-3 text-right tabular-nums">
											<a
												href={`/teacher/assignments/${item.assignment.id}/submissions?status=unsubmitted`}
												class="hover:underline"
												title={$i18n.t('Unsubmitted')}
												on:click|stopPropagation
											>
												{item.submission_count}/{item.student_count}
											</a>
										</td>
										<td class="px-4 py-3 text-right tabular-nums">
											{#if item.pending_review_count > 0}
												<a
													href={`/teacher/assignments/${item.assignment.id}/submissions?status=pending`}
													class="font-semibold text-amber-600 hover:underline dark:text-amber-400"
													on:click|stopPropagation
												>
													{item.pending_review_count}
												</a>
											{:else}
												<span class="text-gray-300 dark:text-gray-600">0</span>
											{/if}
										</td>
										<td class="px-4 py-3 text-right tabular-nums">
											{#if item.returned_count > 0}
												{item.returned_count}
											{:else}
												<span class="text-gray-300 dark:text-gray-600">0</span>
											{/if}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</EduCard>
		{/if}
	</div>

	<ConfirmDialog
		bind:show={showRegenerateConfirm}
		title={$i18n.t('Regenerate Invite Code')}
		message={$i18n.t(
			'The current invite code stops working immediately and any shared invite links become invalid. Continue?'
		)}
		on:confirm={regenerateCode}
	/>
</TeacherPageShell>
