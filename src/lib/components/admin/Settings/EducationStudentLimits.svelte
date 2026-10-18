<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	const i18n: Writable<i18nType> = getContext('i18n');

	// 学生在作业写作区的限制写死在代码里(不能做成开关),这里列出来免得日久忘了;
	// 作业以外能否改参数与系统提示由权限组决定,按后端实际算出的结果显示。
	export let overrides: { params: boolean; system_prompt: boolean };

	const LIMITS = [
		'They cannot change model parameters or add their own system prompt; the chat follows the assignment instructions and the platform settings.',
		'Memory is off, and the built-in tools that search past chats or memories are disabled.',
		'The assignment project folder is maintained by the platform; students cannot rewrite its instructions.'
	];

	const can = (allowed: boolean) => (allowed ? $i18n.t('can') : $i18n.t('cannot'));
</script>

<div
	class="flex flex-col gap-2 rounded-xl border border-gray-100 px-3 py-2.5 dark:border-gray-850"
	data-testid="student-limits"
>
	<div class="text-xs font-medium text-gray-700 dark:text-gray-300">
		{$i18n.t('Fixed limits for students in assignment writing')}
	</div>
	<ul class="flex list-disc flex-col gap-1 pl-4 text-[0.6875rem] text-gray-500 dark:text-gray-400">
		{#each LIMITS as limit}
			<li>{$i18n.t(limit)}</li>
		{/each}
	</ul>
	<p class="text-[0.6875rem] text-gray-400 dark:text-gray-600">
		{$i18n.t('These protect the evidence teachers grade from and cannot be switched off.')}
	</p>

	<div
		class="border-t border-gray-100 pt-2 dark:border-gray-850"
		data-testid="student-permission-status"
	>
		<p class="text-[0.6875rem] text-gray-600 dark:text-gray-400">
			{$i18n.t(
				'Elsewhere (personal writing and ordinary chat), students in the student group {{params}} change model parameters and {{prompt}} add a system prompt.',
				{ params: can(overrides.params), prompt: can(overrides.system_prompt) }
			)}
		</p>
		<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
			{$i18n.t(
				'Group permissions only add up: to restrict students, turn these off in the default permissions and grant them to the teacher group.'
			)}
			<a class="underline" href="/admin/users/groups">{$i18n.t('Open groups')}</a>
		</p>
	</div>
</div>
