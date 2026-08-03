<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { getStudentPerformance } from '$lib/apis/education';
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

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	const getReviewStatusLabel = (value: string) =>
		({
			unsubmitted: t('Unsubmitted'),
			pending: t('Pending Review'),
			reviewed: t('Reviewed'),
			returned: t('Returned')
		})[value] || value;
	const statusTone = (value: string) =>
		({
			unsubmitted: 'gray',
			pending: 'amber',
			reviewed: 'emerald',
			returned: 'rose'
		})[value] || 'gray';

	let performance = null;
	let loading = true;
	let loadError = '';

	onMount(async () => {
		try {
			performance = await getStudentPerformance(
				localStorage.token,
				$page.params.classroomId,
				$page.params.studentUserId
			);
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		} finally {
			loading = false;
		}
	});
</script>

<TeacherPageShell title="Classrooms">
	{#if loading}
		<div class="mx-auto max-w-6xl px-4 py-8 text-sm text-gray-500 dark:text-gray-400">
			{$i18n.t('Loading student performance...')}
		</div>
	{:else if loadError}
		<div class="mx-auto max-w-3xl px-4 py-16">
			<EduStateCard tone="error">{loadError}</EduStateCard>
		</div>
	{:else}
		<div class="mx-auto max-w-6xl px-4 py-8">
			<TeacherSectionNav />

			<div class="mb-6 flex flex-wrap items-end justify-between gap-3">
				<div>
					<div class="mb-2 text-sm text-gray-500 dark:text-gray-400">
						{$i18n.t('Teaching')} / {$i18n.t('Classrooms')} /
						{getClassroomDisplayName(performance.classroom.name, t)} / {$i18n.t('Students')}
					</div>
					<h1 class="text-3xl font-semibold">{performance.student_name}</h1>
					{#if performance.student_email}
						<div class="mt-1 text-sm text-gray-500 dark:text-gray-400">{performance.student_email}</div>
					{/if}
				</div>
				<EduButton
					on:click={() => goto(`/teacher/classrooms/${performance.classroom.id}/students`)}
				>
					{$i18n.t('Back to Students')}
				</EduButton>
			</div>

			<div class="mb-8 grid gap-4 md:grid-cols-5">
				<EduStatCard label="Assignments" value={performance.assignment_count} />
				<EduStatCard label="Submitted" value={performance.submitted_count} />
				<EduStatCard label="Unsubmitted" value={performance.unsubmitted_count} />
				<EduStatCard label="Reviewed" value={performance.reviewed_count} />
				<EduStatCard
					label="Average Score"
					value={performance.average_score != null ? performance.average_score : '—'}
				/>
			</div>

			<EduCard>
				<div class="mb-4 text-sm font-semibold">{$i18n.t('Assignment History')}</div>
				{#if performance.items.length === 0}
					<EduEmpty>{$i18n.t('No assignments yet.')}</EduEmpty>
				{:else}
					<div class="space-y-3">
						{#each performance.items as item}
							<EduTile>
								<div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
									<div>
										<div class="font-medium text-gray-900 dark:text-gray-100">{item.assignment.title}</div>
										<div class="mt-2 flex flex-wrap items-center gap-2 text-xs">
											<EduBadge tone={statusTone(item.review_status)}>
												{getReviewStatusLabel(item.review_status)}
											</EduBadge>
											{#if item.score != null}
												<EduBadge tone="emerald">{$i18n.t('Score')}: {item.score}</EduBadge>
											{/if}
											{#if item.round_no != null && item.round_no > 1}
												<EduBadge>{$i18n.t('Round {{round}}', { round: item.round_no })}</EduBadge>
											{/if}
											{#if item.submitted_at}
												<span class="text-gray-500 dark:text-gray-400">
													{new Date(item.submitted_at * 1000).toLocaleString()}
												</span>
											{/if}
										</div>
										{#if item.submission_id}
											<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500 dark:text-gray-400">
												<div>{$i18n.t('Typed')}: {item.source_stats?.user_typed_chars ?? 0}</div>
												<div>{$i18n.t('AI inserted')}: {item.source_stats?.ai_inserted_chars ?? 0}</div>
												<div>{$i18n.t('AI pasted')}: {item.source_stats?.ai_pasted_chars ?? 0}</div>
												<div>{$i18n.t('Prompts')}: {item.prompt_count}</div>
												<div>
													{$i18n.t('Reflection')}: {item.has_reflection ? t('Yes') : t('No')}
												</div>
											</div>
										{/if}
									</div>
									{#if item.submission_id}
										<EduButton
											variant="primary"
											class="shrink-0 self-start"
											on:click={() => goto(`/teacher/submissions/${item.submission_id}`)}
										>
											{$i18n.t('Open')}
										</EduButton>
									{/if}
								</div>
							</EduTile>
						{/each}
					</div>
				{/if}
			</EduCard>
		</div>
	{/if}
</TeacherPageShell>
