<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { getStudentProfile } from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import StudentGrowthProfile from '$lib/components/education/StudentGrowthProfile.svelte';
	import { getClassroomDisplayName } from '$lib/utils/education';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let profile = null;
	let loading = true;
	let loadError = '';

	onMount(async () => {
		try {
			profile = await getStudentProfile(
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
			{$i18n.t('Loading student profile...')}
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
						{getClassroomDisplayName(profile.classroom?.name, t)} / {$i18n.t('Students')}
					</div>
					<h1 class="text-3xl font-semibold">{profile.student_name}</h1>
					{#if profile.student_email}
						<div class="mt-1 text-sm text-gray-500 dark:text-gray-400">
							{profile.student_email}
						</div>
					{/if}
				</div>
				<EduButton
					on:click={() => goto(`/teacher/classrooms/${$page.params.classroomId}/students`)}
				>
					{$i18n.t('Back to Students')}
				</EduButton>
			</div>

			<StudentGrowthProfile
				{profile}
				variant="teacher"
				on:open={(event) => goto(`/teacher/submissions/${event.detail.submissionId}`)}
			/>
		</div>
	{/if}
</TeacherPageShell>
