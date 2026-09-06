<script lang="ts">
	import { getContext } from 'svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SidebarIcon from '$lib/components/icons/Sidebar.svelte';
	import { mobile, showSidebar } from '$lib/stores';

	const i18n = getContext('i18n');

	// 二级页此前顶栏 H1 写的是分区名(「Classrooms」),而当前对象名(班级名、学生名)
	// 是页面体里的第二个 H1——最显眼的标题不告诉你在看谁,同一页还有两个 H1。
	// 现在顶栏独占面包屑 + 唯一 H1:crumbs 是祖先,title 是当前对象。
	// 两者都由调用方译好再传进来,页面里不再 t() —— 班级名、学生名不是词条,
	// 过一遍 t() 只是碰运气不撞上同名 key。
	export let crumbs: Array<{ label: string; href?: string }> = [];
	export let title = '';
</script>

<div
	class="flex h-screen max-h-[100dvh] w-full max-w-full flex-col transition-width duration-200 ease-in-out {$showSidebar
		? 'md:max-w-[calc(100%-var(--sidebar-width))]'
		: ''}"
>
	<nav class="w-full px-2.5 pt-1.5 backdrop-blur-xl drag-region">
		<div class="flex items-center">
			{#if $mobile}
				<div class="{$showSidebar ? 'md:hidden' : ''} mt-1.5 flex flex-none items-center self-end">
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
				<div class="min-w-0">
					{#if crumbs.length > 0}
						<nav aria-label={$i18n.t('Breadcrumb')} class="flex flex-wrap items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
							{#each crumbs as crumb, index}
								{#if index > 0}
									<span aria-hidden="true" class="text-gray-300 dark:text-gray-600">/</span>
								{/if}
								{#if crumb.href}
									<a href={crumb.href} class="truncate hover:text-gray-800 dark:hover:text-gray-200 hover:underline">
										{crumb.label}
									</a>
								{:else}
									<span class="truncate">{crumb.label}</span>
								{/if}
							{/each}
						</nav>
					{/if}
					<h1 class="truncate text-2xl font-semibold">{title}</h1>
				</div>
				<slot name="nav-actions" />
			</div>
		</div>
	</nav>

	<div class="flex-1 overflow-y-auto">
		<slot />
	</div>
</div>
