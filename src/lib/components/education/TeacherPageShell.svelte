<script lang="ts">
	import { getContext } from 'svelte';
	import { page } from '$app/stores';
	import EduPageShell from './EduPageShell.svelte';
	import { TEACHER_SECTIONS, isTeacherSectionActive, type TeacherNavLink } from './teacher-nav';

	const i18n = getContext('i18n');

	// 教师页骨架 = 通用 EduPageShell + 顶部四个分区 + 面包屑首级「教学」。
	// 面包屑第一级由这里统一补上并可点回总览,调用方不再传。
	export let crumbs: Array<{ label: string; href?: string }> = [];
	export let title = '';
	// 对象级子标签(作业:概况/提交/分析/设置;班级:概况/学生)。
	export let tabs: TeacherNavLink[] = [];
	export let width: '5xl' | '6xl' | 'full' = '6xl';

	$: pathname = $page.url.pathname;
	$: allCrumbs = [{ label: $i18n.t('Teaching'), href: '/teacher' }, ...crumbs];
</script>

<EduPageShell crumbs={allCrumbs} {title} {tabs} {width}>
	<!-- 分区导航是教师端的主入口,做成带底色的分段控件,不能和面包屑一样轻 -->
	<nav
		slot="sections"
		aria-label={$i18n.t('Teaching')}
		class="flex w-fit max-w-full items-center gap-1 overflow-x-auto rounded-xl border border-gray-200 bg-gray-50 p-1 text-sm font-medium dark:border-gray-800 dark:bg-gray-900"
	>
		{#each TEACHER_SECTIONS as section}
			{@const active = isTeacherSectionActive(section.href, pathname)}
			<a
				href={section.href}
				aria-current={active ? 'page' : undefined}
				class="shrink-0 rounded-lg px-4 py-1.5 transition {active
					? 'bg-gray-900 text-white shadow-sm dark:bg-gray-100 dark:text-gray-900'
					: 'text-gray-700 hover:bg-white hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-white'}"
			>
				{$i18n.t(section.label)}
			</a>
		{/each}
	</nav>

	<svelte:fragment slot="nav-actions">
		<slot name="nav-actions" />
	</svelte:fragment>

	<slot />
</EduPageShell>
