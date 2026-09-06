<script lang="ts">
	import { getContext } from 'svelte';
	import Calendar from '$lib/components/icons/Calendar.svelte';

	const i18n = getContext('i18n');

	export let value = '';
	export let required = false;
	export let disabled = false;
	export let className = '';
	export let placeholder = '';

	let input: HTMLInputElement;
	// 空值时原生控件只会显示浏览器界面语言的占位符（中文界面里常是「yyyy/mm/日」这种
	// 混排），页面 lang 和 CSS 都改不动。所以未填且未开始键入时把原生文字调透明、盖上
	// 自己的占位文案；一旦有键盘输入就立刻交还原生控件，分段编辑和校验保持原样。
	let typing = false;

	$: hint = placeholder || $i18n.t('Select date and time');
	$: masked = !value && !typing;

	// Esc（关掉弹窗）、Tab（离开）、Enter（提交表单）都不是在编辑分段，按了它们仍该
	// 盖着占位文案；带修饰键的组合同理。只有真正改动分段的按键才交还原生显示。
	const EDITING_KEYS = /^(?:[0-9]|Arrow(?:Up|Down|Left|Right)|Backspace|Delete)$/;

	const onKeydown = (event: KeyboardEvent) => {
		if (event.ctrlKey || event.metaKey || event.altKey) return;
		if (EDITING_KEYS.test(event.key)) typing = true;
	};

	// 原生的日历按钮固定贴在右边缘，字段一宽就离文字很远。隐掉它，改成整个框可点。
	const openPicker = () => {
		if (disabled) return;
		try {
			input.showPicker();
		} catch {
			// 浏览器拒绝弹出（无用户手势等）时退回普通聚焦，键盘输入仍然可用。
			input.focus();
		}
	};
</script>

<div class="relative">
	<input
		bind:this={input}
		type="datetime-local"
		bind:value
		{required}
		{disabled}
		class="{className} {masked ? 'text-transparent' : ''} {disabled ? '' : 'cursor-pointer'}"
		class:masked
		on:click={openPicker}
		on:keydown={onKeydown}
		on:blur={() => (typing = false)}
		on:change
	/>
	{#if masked}
		<span
			class="pointer-events-none absolute inset-0 flex items-center px-4 text-sm text-gray-400 dark:text-gray-500"
			class:opacity-50={disabled}
		>
			{hint}
		</span>
	{/if}
	<span
		class="pointer-events-none absolute inset-y-0 right-4 flex items-center text-gray-400 dark:text-gray-500"
		class:opacity-50={disabled}
	>
		<Calendar className="size-4" />
	</span>
</div>

<style>
	input::-webkit-calendar-picker-indicator {
		display: none;
	}

	/* 弹窗选中的那一段（年 / 月…）会被 UA 样式画上选区底色和前景色，单靠
	   color: transparent 盖不住，得把整个编辑区一起隐掉。 */
	input.masked::-webkit-datetime-edit,
	input.masked::-webkit-datetime-edit-fields-wrapper {
		opacity: 0;
	}
</style>
