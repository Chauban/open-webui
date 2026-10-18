<script lang="ts">
	import { getContext } from 'svelte';

	import Switch from '$lib/components/common/Switch.svelte';

	const i18n = getContext('i18n');

	// 老师把辅导对话的思考交给学生开关时,输入框上方的一行。开 = 老师设的档位,关 = 不思考直接答;
	// 每条回复实际用的档位由服务端记下,老师批改时看得到。
	export let on = true;
</script>

<div
	class="mx-auto mb-1 flex w-full max-w-6xl items-center justify-end gap-2 px-2.5 text-xs text-gray-500 dark:text-gray-400"
	data-testid="thinking-switch"
>
	<span
		title={$i18n.t(
			'On: the AI thinks before answering, slower but more careful. Off: it answers right away.'
		)}
	>
		{$i18n.t('Deep thinking')}
	</span>
	<Switch bind:state={on} ariaLabel={$i18n.t('Deep thinking')} />
</div>
