<script lang="ts">
	import { getContext } from 'svelte';
	import { page } from '$app/stores';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SidebarIcon from '$lib/components/icons/Sidebar.svelte';
	import { mobile, showSidebar } from '$lib/stores';
	import { TEACHER_SECTIONS, isTeacherSectionActive, type TeacherNavLink } from './teacher-nav';

	const i18n = getContext('i18n');

	// 顶栏独占面包屑 + 唯一 H1:crumbs 是祖先,title 是当前对象。
	// 两者都由调用方译好再传进来 —— 班级名、学生名不是词条,过一遍 t() 只是碰运气。
	// 面包屑第一级「教学」由这里统一补上并可点回总览,调用方不再传。
	export let crumbs: Array<{ label: string; href?: string }> = [];
	export let title = '';
	// 对象级子标签(作业:概况/提交/分析/设置;班级:概况/学生)。标签名是词条 key,这里翻译。
	export let tabs: TeacherNavLink[] = [];

	$: pathname = $page.url.pathname;
	$: allCrumbs = [{ label: $i18n.t('Teaching'), href: '/teacher' }, ...crumbs];
	// 第一个标签是对象首页,只认精确匹配;其余标签的子路由(如学生画像)也算选中。
	$: isTabActive = (tab: TeacherNavLink, index: number) =>
		index === 0 ? pathname === tab.href : pathname === tab.href || pathname.startsWith(`${tab.href}/`);
</script>

<div
	class="flex h-screen max-h-[100dvh] w-full max-w-full flex-col transition-width duration-200 ease-in-out {$showSidebar
		? 'md:max-w-[calc(100%-var(--sidebar-width))]'
		: ''}"
>
	<header
		class="w-full shrink-0 px-2.5 pt-1.5 drag-region {tabs.length > 0
			? 'border-b border-gray-100 dark:border-gray-850'
			: ''}"
	>
		<div class="flex items-start">
			{#if $mobile}
				<div class="{$showSidebar ? 'md:hidden' : ''} mt-1.5 flex flex-none items-center">
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

			<div class="ml-2 min-w-0 flex-1 py-1">
				<div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
					<nav
						aria-label={$i18n.t('Breadcrumb')}
						class="flex min-w-0 flex-wrap items-center gap-1 text-xs text-gray-500 dark:text-gray-400"
					>
						{#each allCrumbs as crumb, index}
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

					<nav aria-label={$i18n.t('Teaching')} class="flex shrink-0 items-center gap-0.5 text-xs">
						{#each TEACHER_SECTIONS as section}
							{@const active = isTeacherSectionActive(section.href, pathname)}
							<a
								href={section.href}
								aria-current={active ? 'page' : undefined}
								class="rounded-full px-3 py-1 transition {active
									? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'
									: 'text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-850 dark:hover:text-gray-100'}"
							>
								{$i18n.t(section.label)}
							</a>
						{/each}
					</nav>
				</div>

				<div class="mt-0.5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
					<h1 class="min-w-0 truncate text-2xl font-semibold">{title}</h1>
					<div class="flex shrink-0 flex-wrap items-center gap-2">
						<slot name="nav-actions" />
					</div>
				</div>

				{#if tabs.length > 0}
					<nav class="-mb-px mt-2 flex gap-1 overflow-x-auto">
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
	</header>

	<div class="min-h-0 flex-1 overflow-y-auto">
		<slot />
	</div>
</div>
