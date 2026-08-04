<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SidebarIcon from '$lib/components/icons/Sidebar.svelte';
	import { mobile, showSidebar } from '$lib/stores';

	import { getMyWritingProfile } from '$lib/apis/education';
	import LoadingState from '$lib/components/education/LoadingState.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import StudentGrowthProfile from '$lib/components/education/StudentGrowthProfile.svelte';

	// 学生看自己的成长画像。教师端看到的是同一个组件、同一套指标——
	// 学生看不到自己的成长，这个模块的教育价值就少一半。
	const i18n = getContext('i18n');

	let profile = null;
	let loaded = false;
	let loadError = '';

	onMount(async () => {
		try {
			profile = await getMyWritingProfile(localStorage.token);
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		} finally {
			loaded = true;
		}
	});
</script>

{#if loaded && !loadError}
	<div
		class="flex h-screen max-h-[100dvh] w-full max-w-full flex-col transition-width duration-200 ease-in-out {$showSidebar
			? 'md:max-w-[calc(100%-var(--sidebar-width))]'
			: ''}"
	>
		<nav class="w-full px-2.5 pt-1.5 backdrop-blur-xl drag-region">
			<div class="flex items-center">
				{#if $mobile}
					<div
						class="{$showSidebar ? 'md:hidden' : ''} mt-1.5 flex flex-none items-center self-end"
					>
						<Tooltip
							content={$showSidebar ? $i18n.t('Close Sidebar') : $i18n.t('Open Sidebar')}
							interactive={true}
						>
							<button
								id="sidebar-toggle-button"
								class="flex cursor-pointer rounded-lg transition hover:bg-gray-100 dark:hover:bg-gray-850"
								on:click={() => showSidebar.set(!$showSidebar)}
							>
								<div class="self-center p-1.5">
									<SidebarIcon />
								</div>
							</button>
						</Tooltip>
					</div>
				{/if}

				<div class="ml-2 flex w-full items-center justify-between py-1">
					<div>
						<div class="text-xs uppercase tracking-[0.2em] text-gray-500 dark:text-gray-400">
							{$i18n.t('Writing')}
						</div>
						<h1 class="text-2xl font-semibold">{$i18n.t('My Growth')}</h1>
					</div>
					<EduButton on:click={() => goto('/me/writing')}>
						{$i18n.t('Back to Writing')}
					</EduButton>
				</div>
			</div>
		</nav>

		<div class="flex-1 overflow-y-auto">
			<div class="mx-auto max-w-6xl px-4 py-8">
				<StudentGrowthProfile {profile} variant="student" />
			</div>
		</div>
	</div>
{:else if loadError}
	<div class="mx-auto max-w-3xl px-4 py-16">
		<EduStateCard tone="error">{loadError}</EduStateCard>
	</div>
{:else}
	<LoadingState messageKey="Loading growth profile..." />
{/if}
