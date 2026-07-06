<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { getTeacherClassroomAssignments, getTeacherClassrooms } from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	const getClassroomDisplayName = (name: string) =>
		name?.trim() === 'Default Classroom' ? t('Default Classroom') : name;

	let classroom = null;
	let assignments = [];
	let loading = true;
	let loadError = '';

	const classroomId = () => $page.params.classroomId;

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
		try {
			const classrooms = await getTeacherClassrooms(localStorage.token);
			classroom = classrooms.find((item) => item.classroom.id === classroomId())?.classroom ?? null;
			if (!classroom) {
				throw new Error('Classroom not found');
			}
			assignments = await getTeacherClassroomAssignments(localStorage.token, classroomId());
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
		<div class="mx-auto max-w-6xl px-4 py-8 text-sm text-gray-500">{$i18n.t('Loading assignments...')}</div>
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
					{$i18n.t('Teaching')} / {$i18n.t('Classrooms')} / {getClassroomDisplayName(classroom.name)}
				</div>
				<h1 class="text-3xl font-semibold">{$i18n.t('Classroom Assignments')}</h1>
			</div>
			<div class="flex flex-wrap gap-2">
				<button
					class="rounded-full border border-gray-300 px-4 py-2 text-sm"
					on:click={() => goto(`/teacher/classrooms/${classroom.id}`)}
				>
					{$i18n.t('Back to Classroom')}
				</button>
				<button
					class="rounded-full bg-black px-4 py-2 text-sm text-white"
					on:click={() => goto(`/teacher/assignments/new?classroomId=${classroom.id}`)}
				>
					{$i18n.t('Create Assignment')}
				</button>
			</div>
		</div>

		{#if assignments.length === 0}
			<div class="rounded-3xl border border-gray-200 bg-white p-6 text-sm text-gray-500">
				{$i18n.t('No assignments yet.')}
			</div>
		{:else}
			<div class="grid gap-4">
				{#each assignments as item}
					<div class="rounded-3xl border border-gray-200 bg-white p-5">
						<div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
							<div>
								<div class="text-lg font-semibold text-gray-900">{item.assignment.title}</div>
								<div class="mt-1 text-sm text-gray-500">
									{item.assignment.description || $i18n.t('No description')}
								</div>
								<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
									<div>{$i18n.t('Students')}: {item.student_count}</div>
									<div>{$i18n.t('Submissions')}: {item.submission_count}</div>
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
	{/if}
</TeacherPageShell>
