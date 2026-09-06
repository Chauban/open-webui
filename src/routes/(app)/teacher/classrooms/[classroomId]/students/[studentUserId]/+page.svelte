<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { getStudentProfile } from '$lib/apis/education';
	import type { StudentProfileFilters, TeacherStudentProfile } from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import StudentGrowthProfile from '$lib/components/education/StudentGrowthProfile.svelte';
	import { getClassroomDisplayName, resolveErrorMessage } from '$lib/utils/education';
	import { createLatestRequestGate } from '$lib/utils/latest-request';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let profile: TeacherStudentProfile | null = null;
	let filters: StudentProfileFilters = {};
	let loading = true;
	let loadError = '';
	const profileRequestGate = createLatestRequestGate();

	const loadProfile = async (nextFilters: StudentProfileFilters = filters) => {
		const requestId = profileRequestGate.next();
		filters = nextFilters;
		loadError = '';
		try {
			const nextProfile = await getStudentProfile(
				localStorage.token,
				$page.params.classroomId,
				$page.params.studentUserId,
				filters
			);
			if (!profileRequestGate.isLatest(requestId)) return;
			profile = nextProfile;
		} catch (error) {
			if (!profileRequestGate.isLatest(requestId)) return;
			loadError = resolveErrorMessage(error, t);
			toast.error(loadError);
		} finally {
			if (profileRequestGate.isLatest(requestId)) loading = false;
		}
	};

	onMount(loadProfile);
</script>

<TeacherPageShell
	crumbs={[
		{ label: $i18n.t('Teaching') },
		{ label: $i18n.t('Classrooms'), href: '/teacher/classrooms' },
		{
			label: getClassroomDisplayName(profile?.classrooms?.[0]?.name, t),
			href: `/teacher/classrooms/${$page.params.classroomId}`
		},
		{
			label: $i18n.t('Students'),
			href: `/teacher/classrooms/${$page.params.classroomId}/students`
		}
	]}
	title={profile?.student_name ?? $i18n.t('Students')}
>
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
				<div class="text-sm text-gray-500 dark:text-gray-400">
					{profile.student_email ?? ''}
				</div>
				<EduButton
					on:click={() => goto(`/teacher/classrooms/${$page.params.classroomId}/students`)}
				>
					{$i18n.t('Back to Students')}
				</EduButton>
			</div>

			<StudentGrowthProfile
				{profile}
				{filters}
				variant="teacher"
				on:open={(event) => goto(`/teacher/submissions/${event.detail.submissionId}`)}
				on:filter={(event) => loadProfile(event.detail)}
			/>
		</div>
	{/if}
</TeacherPageShell>
