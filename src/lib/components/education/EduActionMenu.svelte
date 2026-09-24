<script lang="ts">
	import { getContext } from 'svelte';
	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import DropdownMenu from '$lib/components/common/DropdownMenu.svelte';
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte';

	// 列表行的次要操作收进「⋯」:此前每行摆 3–5 个同样醒目的按钮,
	// 主操作(进入对象)被淹没。label 是词条 key,这里翻译。
	export let items: Array<{ label: string; onClick: () => void; danger?: boolean }> = [];

	const i18n = getContext('i18n');
	let show = false;
</script>

<!-- 行本身可点击进入对象;菜单外包一层拦住冒泡,点「⋯」不跳走。 -->
<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div class="inline-flex" on:click|stopPropagation>
<Dropdown bind:show align="end">
	<button
		type="button"
		aria-label={$i18n.t('More')}
		class="flex size-8 items-center justify-center rounded-full text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"
	>
		<EllipsisHorizontal className="size-4" />
	</button>

	<div slot="content">
		<DropdownMenu className="min-w-[10rem]">
			{#each items as item}
				<button
					type="button"
					class="flex w-full cursor-pointer select-none items-center rounded-xl px-3 py-1.5 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800 {item.danger
						? 'text-red-600 dark:text-red-400'
						: ''}"
					on:click|stopPropagation={() => {
						show = false;
						item.onClick();
					}}
				>
					{$i18n.t(item.label)}
				</button>
			{/each}
		</DropdownMenu>
	</div>
</Dropdown>
</div>
