<script lang="ts">
	import { getContext } from 'svelte';
	import { page } from '$app/stores';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SidebarIcon from '$lib/components/icons/Sidebar.svelte';
	import { mobile, showSidebar } from '$lib/stores';

	const i18n = getContext('i18n');

	// 教学模块的整页骨架,教师端(TeacherPageShell)与学生端共用。
	// 页头内容与正文共用同一条栏宽:此前页头贴满屏幕、正文居中,
	// 顶栏按钮被甩到屏幕最右上角,和它所操作的列表隔得老远。
	// width 要和页面正文容器的 max-w 一致;批改工作台正文铺满,用 full。
	export let width: '4xl' | '5xl' | '6xl' | 'full' = '6xl';
	// crumbs 是祖先,title 是当前对象;都由调用方译好再传 —— 班级名、学生名不是词条。
	export let crumbs: Array<{ label: string; href?: string }> = [];
	export let title = '';
	// 子标签:标签名是词条 key,这里翻译。
	export let tabs: Array<{ label: string; href: string }> = [];

	const WIDTH_CLASS = {
		'4xl': 'max-w-4xl',
		'5xl': 'max-w-5xl',
		'6xl': 'max-w-6xl',
		full: 'max-w-none'
	};

	$: pathname = $page.url.pathname;
	// 第一个标签是对象首页,只认精确匹配;其余标签的子路由(如学生画像)也算选中。
	$: isTabActive = (tab: { href: string }, index: number) =>
		index === 0 ? pathname === tab.href : pathname === tab.href || pathname.startsWith(`${tab.href}/`);
</script>

<div
	class="flex h-screen max-h-[100dvh] w-full max-w-full flex-col transition-width duration-200 ease-in-out {$showSidebar
		? 'md:max-w-[calc(100%-var(--sidebar-width))]'
		: ''}"
>
	<header
		class="w-full shrink-0 drag-region {tabs.length > 0
			? 'border-b border-gray-100 dark:border-gray-850'
			: ''}"
	>
		<div class="flex items-start">
			{#if $mobile}
				<div class="{$showSidebar ? 'md:hidden' : ''} ml-2.5 mt-3 flex flex-none items-center">
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

			<div class="min-w-0 flex-1">
				<div
					class="mx-auto w-full {WIDTH_CLASS[width]} {width === 'full' ? 'px-6' : 'px-4'} pt-3"
				>
					<!-- 分区导航(教师端四个分区);学生端没有 -->
					<slot name="sections" />

					{#if crumbs.length > 0}
						<nav
							aria-label={$i18n.t('Breadcrumb')}
							class="{$$slots.sections
								? 'mt-4'
								: 'mt-1'} flex min-w-0 flex-wrap items-center gap-1 text-xs text-gray-500 dark:text-gray-400"
						>
							{#each crumbs as crumb, index}
								{#if index > 0}
									<span aria-hidden="true" class="text-gray-300 dark:text-gray-600">/</span>
								{/if}
								{#if crumb.href}
									<a
										href={crumb.href}
										class="max-w-48 truncate hover:text-gray-800 hover:underline dark:hover:text-gray-200"
									>
										{crumb.label}
									</a>
								{:else}
									<span class="max-w-48 truncate">{crumb.label}</span>
								{/if}
							{/each}
						</nav>
					{/if}

					<!-- 页面主操作(新建班级/新建作业…)放在标题同一行的右端,与正文右边缘对齐 -->
					<div
						class="{crumbs.length > 0
							? 'mt-1'
							: $$slots.sections
								? 'mt-4'
								: 'mt-2'} flex flex-wrap items-center justify-between gap-x-4 gap-y-2"
					>
						<h1 class="min-w-0 truncate text-2xl font-semibold">{title}</h1>
						<div class="flex shrink-0 flex-wrap items-center gap-2">
							<slot name="nav-actions" />
						</div>
					</div>

					{#if tabs.length > 0}
						<nav class="-mx-3 -mb-px mt-3 flex gap-1 overflow-x-auto">
							{#each tabs as tab, index}
								{@const active = isTabActive(tab, index)}
								<a
									href={tab.href}
									aria-current={active ? 'page' : undefined}
									class="shrink-0 border-b-2 px-3 pb-2 pt-1 text-sm font-medium transition {active
										? 'border-gray-900 text-gray-900 dark:border-gray-100 dark:text-gray-100'
										: 'border-transparent text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200'}"
								>
									{$i18n.t(tab.label)}
								</a>
							{/each}
						</nav>
					{/if}
				</div>
			</div>
		</div>
	</header>

	<div class="min-h-0 flex-1 overflow-y-auto">
		<slot />
	</div>
</div>
