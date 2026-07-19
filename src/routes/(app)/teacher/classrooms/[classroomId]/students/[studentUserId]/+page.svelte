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

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	const getClassroomDisplayName = (name: string) =>
		name?.trim() === 'Default Classroom' ? t('Default Classroom') : name;
	const getReviewStatusLabel = (value: string) =>
		({
			unsubmitted: t('Unsubmitted'),
			pending: t('Pending Review'),
			reviewed: t('Reviewed'),
			returned: t('Returned')
		})[value] || value;
	const statusTone = (value: string) =>
		({
			unsubmitted: 'border-gray-200 bg-gray-50 text-gray-600',
			pending: 'border-amber-200 bg-amber-50 text-amber-700',
			reviewed: 'border-emerald-200 bg-emerald-50 text-emerald-700',
			returned: 'border-rose-200 bg-rose-50 text-rose-700'
		})[value] || 'border-gray-200 bg-gray-50 text-gray-600';

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
		<div class="mx-auto max-w-6xl px-4 py-8 text-sm text-gray-500">
			{$i18n.t('Loading student performance...')}
		</div>
	{:else if loadError}
		<div class="mx-auto max-w-3xl px-4 py-16">
			<div class="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
				{loadError}
			</div>
		</div>
	{:else}
		<div class="mx-auto max-w-6xl px-4 py-8">
			<TeacherSectionNav />

			<div class="mb-6 flex flex-wrap items-end justify-between gap-3">
				<div>
					<div class="mb-2 text-sm text-gray-500">
						{$i18n.t('Teaching')} / {$i18n.t('Classrooms')} /
						{getClassroomDisplayName(performance.classroom.name)} / {$i18n.t('Students')}
					</div>
					<h1 class="text-3xl font-semibold">{performance.student_name}</h1>
					{#if performance.student_email}
						<div class="mt-1 text-sm text-gray-500">{performance.student_email}</div>
					{/if}
				</div>
				<button
					class="rounded-full border border-gray-300 px-4 py-2 text-sm"
					on:click={() => goto(`/teacher/classrooms/${performance.classroom.id}/students`)}
				>
					{$i18n.t('Back to Students')}
				</button>
			</div>

			<div class="mb-8 grid gap-4 md:grid-cols-5">
				<div class="rounded-3xl border border-gray-200 bg-white p-5">
					<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('Assignments')}</div>
					<div class="mt-2 text-3xl font-semibold">{performance.assignment_count}</div>
				</div>
				<div class="rounded-3xl border border-gray-200 bg-white p-5">
					<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('Submitted')}</div>
					<div class="mt-2 text-3xl font-semibold">{performance.submitted_count}</div>
				</div>
				<div class="rounded-3xl border border-gray-200 bg-white p-5">
					<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('Unsubmitted')}</div>
					<div class="mt-2 text-3xl font-semibold">{performance.unsubmitted_count}</div>
				</div>
				<div class="rounded-3xl border border-gray-200 bg-white p-5">
					<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('Reviewed')}</div>
					<div class="mt-2 text-3xl font-semibold">{performance.reviewed_count}</div>
				</div>
				<div class="rounded-3xl border border-gray-200 bg-white p-5">
					<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('Average Score')}</div>
					<div class="mt-2 text-3xl font-semibold">
						{performance.average_score != null ? performance.average_score : '—'}
					</div>
				</div>
			</div>

			<div class="rounded-3xl border border-gray-200 bg-white p-5">
				<div class="mb-4 text-sm font-semibold">{$i18n.t('Assignment History')}</div>
				{#if performance.items.length === 0}
					<div class="rounded-2xl border border-dashed border-gray-300 px-4 py-5 text-sm text-gray-500">
						{$i18n.t('No assignments yet.')}
					</div>
				{:else}
					<div class="space-y-3">
						{#each performance.items as item}
							<div class="rounded-2xl border border-gray-200 px-4 py-4 text-sm">
								<div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
									<div>
										<div class="font-medium text-gray-900">{item.assignment.title}</div>
										<div class="mt-2 flex flex-wrap items-center gap-2 text-xs">
											<span class={`rounded-full border px-3 py-1 ${statusTone(item.review_status)}`}>
												{getReviewStatusLabel(item.review_status)}
											</span>
											{#if item.score != null}
												<span class="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-emerald-700">
													{$i18n.t('Score')}: {item.score}
												</span>
											{/if}
											{#if item.round_no != null && item.round_no > 1}
												<span class="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-gray-600">
													{$i18n.t('Round {{round}}', { round: item.round_no })}
												</span>
											{/if}
											{#if item.submitted_at}
												<span class="text-gray-500">
													{new Date(item.submitted_at * 1000).toLocaleString()}
												</span>
											{/if}
										</div>
										{#if item.submission_id}
											<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
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
										<button
											class="shrink-0 self-start rounded-full bg-black px-3 py-2 text-sm text-white"
											on:click={() => goto(`/teacher/submissions/${item.submission_id}`)}
										>
											{$i18n.t('Open')}
										</button>
									{/if}
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		</div>
	{/if}
</TeacherPageShell>
