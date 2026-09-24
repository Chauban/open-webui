<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { getStudentProfile } from '$lib/apis/education';
	import type { StudentProfileFilters, TeacherStudentProfile } from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import { classroomTabs } from '$lib/components/education/teacher-nav';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import StudentGrowthProfile from '$lib/components/education/StudentGrowthProfile.svelte';
	import { getClassroomDisplayName, resolveErrorMessage } from '$lib/utils/education';
	import { createLatestRequestGate } from '$lib/utils/latest-request';

	const i18n = getContext<Writable<i18nType>>('i18n');
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
		{ label: $i18n.t('Classrooms'), href: '/teacher/classrooms' },
		{
			label: getClassroomDisplayName(profile?.classrooms?.[0]?.name, t),
			href: `/teacher/classrooms/${$page.params.classroomId}`
		}
	]}
	title={profile?.student_name ?? ''}
	tabs={classroomTabs($page.params.classroomId)}
>
	<div class="mx-auto max-w-6xl px-4 py-6">
		{#if loading}
			<EduStateCard>{$i18n.t('Loading student profile...')}</EduStateCard>
		{:else if loadError}
			<EduStateCard tone="error">{loadError}</EduStateCard>
		{:else}
			{#if profile.student_email}
				<div class="mb-4 text-sm text-gray-500 dark:text-gray-400">{profile.student_email}</div>
			{/if}
			<StudentGrowthProfile
				{profile}
				{filters}
				variant="teacher"
				reviewClassroomId={$page.params.classroomId}
				on:open={(event) => goto(`/teacher/submissions/${event.detail.submissionId}`)}
				on:filter={(event) => loadProfile(event.detail)}
			/>
		{/if}
	</div>
</TeacherPageShell>
