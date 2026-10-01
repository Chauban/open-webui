<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext, onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { getMyWritingProfile } from '$lib/apis/education';
	import type { StudentProfile, StudentProfileFilters } from '$lib/apis/education';
	import { resolveErrorMessage } from '$lib/utils/education';
	import LoadingState from '$lib/components/education/LoadingState.svelte';
	import EduPageShell from '$lib/components/education/EduPageShell.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import StudentGrowthProfile from '$lib/components/education/StudentGrowthProfile.svelte';
	import { createLatestRequestGate } from '$lib/utils/latest-request';

	// 学生看自己的成长画像。教师端看到的是同一个组件、同一套指标——
	// 学生看不到自己的成长，这个模块的教育价值就少一半。
	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let profile: StudentProfile | null = null;
	let filters: StudentProfileFilters = {};
	let loaded = false;
	let loadError = '';
	const profileRequestGate = createLatestRequestGate();

	const loadProfile = async (nextFilters: StudentProfileFilters = filters) => {
		const requestId = profileRequestGate.next();
		filters = nextFilters;
		loadError = '';
		try {
			const nextProfile = await getMyWritingProfile(localStorage.token, filters);
			if (!profileRequestGate.isLatest(requestId)) return;
			profile = nextProfile;
		} catch (error) {
			if (!profileRequestGate.isLatest(requestId)) return;
			loadError = resolveErrorMessage(error, t);
			toast.error(loadError);
		} finally {
			if (profileRequestGate.isLatest(requestId)) loaded = true;
		}
	};

	onMount(loadProfile);
</script>

{#if loaded && !loadError}
	<EduPageShell
		crumbs={[{ label: $i18n.t('Writing'), href: '/me/writing' }]}
		title={$i18n.t('My Growth')}
	>
		<div class="mx-auto max-w-6xl px-4 py-6">
			<StudentGrowthProfile
				{profile}
				{filters}
				variant="student"
				on:filter={(event) => loadProfile(event.detail)}
			/>
		</div>
	</EduPageShell>
{:else if loadError}
	<div class="mx-auto max-w-3xl px-4 py-16">
		<EduStateCard tone="error">{loadError}</EduStateCard>
	</div>
{:else}
	<LoadingState messageKey="Loading growth profile..." />
{/if}
