<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import type { AutoRetryPolicy, RetryScope } from '$lib/apis/education';
	import Switch from '$lib/components/common/Switch.svelte';
	import { RETRY_SCOPE_TEXT } from '$lib/utils/ai-steps';

	const i18n: Writable<i18nType> = getContext('i18n');

	// 服务商一时出错时哪些模型调用自动重发。行由后端登记(ai_steps.py 的 RETRY_SCOPES)下发,
	// 发请求时是否重发也读那张表:始终重发的只写明,管理员能开关的给开关。
	export let scopes: RetryScope[] = [];
	export let policy: AutoRetryPolicy;
	export let onChange: (policy: AutoRetryPolicy) => void = () => {};

	const toggleKey = (scope: RetryScope) => scope.key as keyof AutoRetryPolicy;
</script>

<div class="flex flex-col gap-3" data-testid="auto-retry-settings">
	<div>
		<div class="text-xs font-medium text-gray-700 dark:text-gray-300">
			{$i18n.t('Automatic retries')}
		</div>
		<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
			{$i18n.t(
				'When the AI provider has a brief problem (rate limit, server error, connection drop or timeout), the request is sent again automatically, up to 4 times, before any reply reaches the student.'
			)}
		</p>
	</div>

	<div class="divide-y divide-gray-100 dark:divide-gray-850">
		{#each scopes as scope (scope.key)}
			<div
				class="flex items-start justify-between gap-4 py-2"
				data-testid={`auto-retry-${scope.key}`}
			>
				<div class="min-w-0">
					<div class="text-xs text-gray-700 dark:text-gray-300">
						{$i18n.t(RETRY_SCOPE_TEXT[scope.key].title)}
					</div>
					<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
						{$i18n.t(RETRY_SCOPE_TEXT[scope.key].hint)}
					</p>
				</div>
				{#if scope.admin_toggle}
					<Switch
						state={policy[toggleKey(scope)]}
						ariaLabel={$i18n.t(RETRY_SCOPE_TEXT[scope.key].title)}
						on:change={(event) => onChange({ ...policy, [toggleKey(scope)]: event.detail })}
					/>
				{:else}
					<span class="shrink-0 text-[0.6875rem] text-gray-500 dark:text-gray-400">
						{$i18n.t('Always on')}
					</span>
				{/if}
			</div>
		{/each}
	</div>
</div>
