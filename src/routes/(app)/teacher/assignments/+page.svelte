<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';
	import dayjs from '$lib/dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';

	import { getTeacherAssignments, getTeacherClassrooms } from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import EduActionMenu from '$lib/components/education/EduActionMenu.svelte';
	import EduBadge from '$lib/components/education/EduBadge.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import {
		formatEpoch,
		getAssignmentStatusLabel,
		getClassroomDisplayName,
		resolveErrorMessage
	} from '$lib/utils/education';

	// 作业列表:整行进入作业,每行只露「截止 · 已交 x/y · 待批改 n」这三个要处理的数,
	// 次要操作收进「⋯」。班级页的「本班作业」也落到这里(?classroom=),不再单独一页。

	dayjs.extend(relativeTime);

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	const FIELD =
		'rounded-full border border-gray-300 bg-white px-3 py-2 text-sm outline-none dark:border-gray-700 dark:bg-gray-850';

	let assignments = [];
	let classrooms = [];
	let loading = true;
	let loadError = '';
	let selectedClassroom = $page.url.searchParams.get('classroom') || 'all';
	let selectedStatus = 'active';
	let sortBy = 'due';
	let keyword = '';

	const isPastDue = (item) =>
		item.assignment.status === 'active' &&
		item.assignment.due_at &&
		item.assignment.due_at * 1000 < Date.now();

	// 默认顺序:还没截止的按截止由近到远在前,已截止/已归档的按截止由近到远在后。
	const dueOrder = (item) => {
		const due = item.assignment.due_at ?? 0;
		const upcoming = item.assignment.status === 'active' && due * 1000 >= Date.now();
		return upcoming ? [0, due] : [1, -due];
	};

	$: filteredAssignments = assignments
		.filter((item) => {
			const matchesClassroom =
				selectedClassroom === 'all' || item.classroom?.id === selectedClassroom;
			const normalizedKeyword = keyword.trim().toLowerCase();
			const matchesKeyword =
				!normalizedKeyword ||
				item.assignment.title.toLowerCase().includes(normalizedKeyword) ||
				(item.assignment.description ?? '').toLowerCase().includes(normalizedKeyword);
			const matchesStatus =
				selectedStatus === 'all' ||
				(selectedStatus === 'active' && item.assignment.status === 'active') ||
				(selectedStatus === 'past_due' && isPastDue(item)) ||
				(selectedStatus === 'archived' && item.assignment.status === 'archived') ||
				(selectedStatus === 'needs_review' && item.pending_review_count > 0);
			return matchesClassroom && matchesKeyword && matchesStatus;
		})
		.sort((a, b) => {
			if (sortBy === 'pending') return b.pending_review_count - a.pending_review_count;
			if (sortBy === 'latest') return (b.latest_submission_at ?? 0) - (a.latest_submission_at ?? 0);
			const [groupA, keyA] = dueOrder(a);
			const [groupB, keyB] = dueOrder(b);
			return groupA - groupB || keyA - keyB;
		});

	const copyWriteLink = async (assignmentId: string) => {
		const link = `${window.location.origin}/assignments/${assignmentId}/write`;
		try {
			await navigator.clipboard.writeText(link);
			toast.success(t('Write link copied.'));
		} catch {
			toast.error(t('Failed to copy write link.'));
		}
	};

	const menuItems = (assignmentId: string) => [
		{ label: 'Copy Student Link', onClick: () => copyWriteLink(assignmentId) },
		{
			label: 'Duplicate as New Assignment',
			onClick: () => goto(`/teacher/assignments/new?from=${assignmentId}`)
		},
		{ label: 'Assignment Analysis', onClick: () => goto(`/teacher/assignments/${assignmentId}/dashboard`) },
		{ label: 'Settings', onClick: () => goto(`/teacher/assignments/${assignmentId}/settings`) }
	];

	onMount(async () => {
		try {
			[assignments, classrooms] = await Promise.all([
				getTeacherAssignments(localStorage.token),
				getTeacherClassrooms(localStorage.token)
			]);
		} catch (error) {
			loadError = resolveErrorMessage(error, t);
			toast.error(loadError);
		} finally {
			loading = false;
		}
	});
</script>

<TeacherPageShell title={$i18n.t('Assignments')}>
	<svelte:fragment slot="nav-actions">
		<EduButton
			variant="primary"
			size="sm"
			on:click={() =>
				goto(
					selectedClassroom === 'all'
						? '/teacher/assignments/new'
						: `/teacher/assignments/new?classroomId=${selectedClassroom}`
				)}
		>
			{$i18n.t('New Assignment')}
		</EduButton>
	</svelte:fragment>

	<div class="mx-auto max-w-6xl px-4 py-6">
		<div class="mb-4 flex flex-wrap items-center gap-2">
			<select class={FIELD} aria-label={$i18n.t('Classroom')} bind:value={selectedClassroom}>
				<option value="all">{$i18n.t('All Classrooms')}</option>
				{#each classrooms as item}
					<option value={item.classroom.id}>{getClassroomDisplayName(item.classroom.name, t)}</option>
				{/each}
			</select>
			<select class={FIELD} aria-label={$i18n.t('Status')} bind:value={selectedStatus}>
				<option value="active">{$i18n.t('Ongoing')}</option>
				<option value="needs_review">{$i18n.t('Has submissions to review')}</option>
				<option value="past_due">{$i18n.t('Past Due')}</option>
				<option value="archived">{$i18n.t('Archived')}</option>
				<option value="all">{$i18n.t('All')}</option>
			</select>
			<select class={FIELD} aria-label={$i18n.t('Sort')} bind:value={sortBy}>
				<option value="due">{$i18n.t('Sort by Due Time')}</option>
				<option value="pending">{$i18n.t('Sort by To Review')}</option>
				<option value="latest">{$i18n.t('Sort by Latest Submission')}</option>
			</select>
			<input
				bind:value={keyword}
				class="{FIELD} min-w-48 flex-1"
				placeholder={$i18n.t('Search assignments')}
			/>
		</div>

		{#if loadError}
			<EduStateCard tone="error">{loadError}</EduStateCard>
		{:else if loading}
			<EduStateCard>{$i18n.t('Loading assignments...')}</EduStateCard>
		{:else if filteredAssignments.length === 0}
			<EduStateCard>
				{assignments.length === 0
					? $i18n.t('No assignments yet.')
					: $i18n.t('No assignments match the current filters.')}
			</EduStateCard>
		{:else}
			<EduCard padding="none">
				<div class="overflow-x-auto">
					<table class="w-full min-w-[44rem] text-sm">
						<thead class="bg-gray-50 text-left text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400">
							<tr>
								<th class="px-4 py-2.5 font-medium">{$i18n.t('Assignment')}</th>
								<th class="px-4 py-2.5 font-medium">{$i18n.t('Due At')}</th>
								<th class="px-4 py-2.5 text-right font-medium">{$i18n.t('Submitted')}</th>
								<th class="px-4 py-2.5 text-right font-medium">{$i18n.t('To Review')}</th>
								<th class="w-12"></th>
							</tr>
						</thead>
						<tbody>
							{#each filteredAssignments as item (item.assignment.id)}
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
										<div class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
											{item.classroom ? getClassroomDisplayName(item.classroom.name, t) : t('Unknown')}
										</div>
									</td>
									<td class="whitespace-nowrap px-4 py-3" title={formatEpoch(item.assignment.due_at)}>
										<div class={isPastDue(item) ? 'text-rose-600 dark:text-rose-400' : ''}>
											{formatEpoch(item.assignment.due_at)}
										</div>
										<div class="text-xs text-gray-400">
											{dayjs(item.assignment.due_at * 1000)
												.locale($i18n.language)
												.fromNow()}
										</div>
									</td>
									<td class="px-4 py-3 text-right tabular-nums">
										{item.submission_count}/{item.student_count}
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
									<td class="px-2 py-3 text-right">
										<EduActionMenu items={menuItems(item.assignment.id)} />
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</EduCard>
		{/if}
	</div>
</TeacherPageShell>
