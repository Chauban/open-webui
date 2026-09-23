<script lang="ts">
	import { getContext, onDestroy, tick } from 'svelte';
	import Calendar from '$lib/components/icons/Calendar.svelte';
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte';
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte';
	import { formatDateTimeInput } from '$lib/utils/education';

	const i18n = getContext('i18n');

	// value 仍是 `YYYY-MM-DDTHH:mm` 本地时间串，和原生 datetime-local 一致，调用方不用改换算。
	export let value = '';
	export let required = false;
	export let disabled = false;
	export let className = '';
	export let placeholder = '';
	// 新选一天时默认落在的时刻：截止时间多是当天结束。
	export let defaultTime = '23:59';

	// 原生 datetime-local 的显示格式跟浏览器语言走（中文界面里会冒出 yyyy/mm/dd），
	// 弹出面板也改不了样式，所以整个换成自绘：框里只显示按界面语言格式化后的完整时间。
	// 日期和时刻要分两步选，任何一步都不自动收起，统一点「确认」写回；Esc / 点外面放弃改动。

	const pad = (n: number) => String(n).padStart(2, '0');
	const HOURS = Array.from({ length: 24 }, (_, i) => i);
	const MINUTES = Array.from({ length: 60 }, (_, i) => i);

	let trigger: HTMLButtonElement;
	let panel: HTMLDivElement;
	let hourList: HTMLDivElement;
	let minuteList: HTMLDivElement;
	let open = false;
	let panelStyle = '';

	// 面板里的草稿，确认前不动 value。
	let draftDate = ''; // YYYY-MM-DD
	let draftHour = 23;
	let draftMinute = 59;
	let viewYear = 0;
	let viewMonth = 0; // 0-11

	const parse = (text: string) => {
		const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(text ?? '');
		return match
			? { date: `${match[1]}-${match[2]}-${match[3]}`, hour: +match[4], minute: +match[5] }
			: null;
	};

	const dateKey = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
	const todayKey = () => dateKey(new Date());

	$: display = formatDateTimeInput(value);
	$: hint = placeholder || $i18n.t('Select date and time');

	// 界面语言决定周首日与星期、月份写法；Intl 不认识时退回浏览器默认。
	const resolveLocale = (language: string | undefined) => {
		try {
			return Intl.DateTimeFormat.supportedLocalesOf(language ?? [])[0];
		} catch {
			return undefined;
		}
	};

	$: locale = resolveLocale($i18n.language);
	$: mondayFirst = !/^en-US/i.test(locale ?? navigator.language);
	$: monthTitle = new Intl.DateTimeFormat(locale, { year: 'numeric', month: 'long' }).format(
		new Date(viewYear, viewMonth, 1)
	);
	$: weekdays = Array.from({ length: 7 }, (_, i) =>
		new Intl.DateTimeFormat(locale, { weekday: 'narrow' }).format(
			// 2024-01-07 是周日。
			new Date(2024, 0, 7 + i + (mondayFirst ? 1 : 0))
		)
	);
	$: days = buildDays(viewYear, viewMonth, mondayFirst);

	const buildDays = (year: number, month: number, monday: boolean) => {
		const first = new Date(year, month, 1);
		const offset = (first.getDay() - (monday ? 1 : 0) + 7) % 7;
		return Array.from({ length: 42 }, (_, i) => {
			const d = new Date(year, month, 1 - offset + i);
			return { key: dateKey(d), day: d.getDate(), inMonth: d.getMonth() === month };
		});
	};

	const timeClass = (active: boolean) =>
		active
			? 'bg-black text-white dark:bg-gray-100 dark:text-gray-900'
			: 'hover:bg-gray-100 dark:hover:bg-gray-800';

	const shiftMonth = (delta: number) => {
		const d = new Date(viewYear, viewMonth + delta, 1);
		viewYear = d.getFullYear();
		viewMonth = d.getMonth();
	};

	const place = () => {
		if (!trigger || !panel) return;
		const rect = trigger.getBoundingClientRect();
		const height = panel.offsetHeight;
		const width = panel.offsetWidth;
		const margin = 8;
		const below = window.innerHeight - rect.bottom;
		const top =
			below >= height + margin || rect.top < height + margin
				? rect.bottom + margin
				: rect.top - height - margin;
		const left = Math.max(margin, Math.min(rect.left, window.innerWidth - width - margin));
		panelStyle = `top:${Math.max(margin, top)}px;left:${left}px;`;
	};

	const scrollTimeIntoView = () => {
		for (const list of [hourList, minuteList]) {
			const active = list?.querySelector<HTMLElement>('[data-active="true"]');
			if (list && active)
				list.scrollTop = active.offsetTop - list.clientHeight / 2 + active.offsetHeight / 2;
		}
	};

	const openPanel = async () => {
		if (disabled) return;
		const current = parse(value);
		const [defaultHour, defaultMinute] = defaultTime.split(':').map(Number);
		draftDate = current?.date ?? '';
		draftHour = current?.hour ?? defaultHour;
		draftMinute = current?.minute ?? defaultMinute;
		const anchor = new Date(`${current?.date ?? todayKey()}T00:00`);
		viewYear = anchor.getFullYear();
		viewMonth = anchor.getMonth();
		open = true;
		await tick();
		place();
		scrollTimeIntoView();
		panel?.focus();
	};

	const closePanel = (refocus = true) => {
		open = false;
		if (refocus) trigger?.focus();
	};

	const confirm = () => {
		if (!draftDate) return;
		value = `${draftDate}T${pad(draftHour)}:${pad(draftMinute)}`;
		closePanel();
	};

	const clear = () => {
		value = '';
		closePanel();
	};

	const onWindowPointerDown = (event: PointerEvent) => {
		if (!open) return;
		const target = event.target as Node;
		if (panel?.contains(target) || trigger?.contains(target)) return;
		closePanel(false);
	};

	const onPanelKeydown = (event: KeyboardEvent) => {
		if (event.key === 'Escape') {
			event.preventDefault();
			event.stopPropagation();
			closePanel();
		} else if (event.key === 'Enter' && draftDate) {
			event.preventDefault();
			confirm();
		}
	};

	onDestroy(() => (open = false));
</script>

<svelte:window
	on:pointerdown={onWindowPointerDown}
	on:resize={() => open && place()}
	on:scroll|capture={() => open && place()}
/>

<div class="relative">
	<button
		bind:this={trigger}
		type="button"
		{disabled}
		class="{className} flex items-center justify-between gap-3 text-left {disabled
			? 'cursor-not-allowed opacity-50'
			: 'cursor-pointer'}"
		aria-haspopup="dialog"
		aria-expanded={open}
		on:click={() => (open ? closePanel() : openPanel())}
	>
		<span class="truncate {display ? '' : 'text-gray-400 dark:text-gray-500'}">
			{display || hint}
		</span>
		<Calendar className="size-4 shrink-0 text-gray-400 dark:text-gray-500" />
	</button>
	<!-- 表单原生校验只认 input：用一个不可见的 input 承载 required，提示气泡会落在字段上。 -->
	{#if required}
		<input
			tabindex="-1"
			aria-hidden="true"
			class="pointer-events-none absolute inset-x-0 bottom-0 h-px w-full opacity-0"
			{value}
			{required}
			{disabled}
			on:focus={() => trigger.focus()}
		/>
	{/if}
</div>

{#if open}
	<!-- svelte-ignore a11y-no-noninteractive-tabindex -->
	<div
		bind:this={panel}
		role="dialog"
		tabindex="-1"
		style={panelStyle}
		class="fixed z-[100] flex w-[22rem] max-w-[calc(100vw-1rem)] flex-col rounded-2xl border border-gray-200 bg-white p-3 text-sm shadow-xl outline-none dark:border-gray-800 dark:bg-gray-850 dark:text-gray-100"
		on:keydown={onPanelKeydown}
	>
		<div class="flex gap-3">
			<div class="min-w-0 flex-1">
				<div class="mb-2 flex items-center justify-between">
					<button
						type="button"
						class="rounded-lg p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800"
						aria-label={$i18n.t('Previous month')}
						on:click={() => shiftMonth(-1)}
					>
						<ChevronLeft className="size-4" />
					</button>
					<div class="font-medium">{monthTitle}</div>
					<button
						type="button"
						class="rounded-lg p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800"
						aria-label={$i18n.t('Next month')}
						on:click={() => shiftMonth(1)}
					>
						<ChevronRight className="size-4" />
					</button>
				</div>
				<div class="grid grid-cols-7 text-center text-xs text-gray-400 dark:text-gray-500">
					{#each weekdays as weekday}
						<div class="py-1">{weekday}</div>
					{/each}
				</div>
				<div class="grid grid-cols-7 gap-y-0.5 text-center">
					{#each days as cell (cell.key)}
						{@const selected = cell.key === draftDate}
						{@const today = cell.key === todayKey()}
						<button
							type="button"
							class="mx-auto flex size-8 items-center justify-center rounded-full text-sm transition
								{selected
								? 'bg-black text-white dark:bg-gray-100 dark:text-gray-900'
								: cell.inMonth
									? 'hover:bg-gray-100 dark:hover:bg-gray-800'
									: 'text-gray-300 hover:bg-gray-100 dark:text-gray-600 dark:hover:bg-gray-800'}
								{today && !selected ? 'font-semibold ring-1 ring-gray-300 dark:ring-gray-600' : ''}"
							on:click={() => {
								draftDate = cell.key;
								if (!cell.inMonth) {
									const d = new Date(`${cell.key}T00:00`);
									viewYear = d.getFullYear();
									viewMonth = d.getMonth();
								}
							}}
						>
							{cell.day}
						</button>
					{/each}
				</div>
			</div>

			<div class="flex gap-1 border-l border-gray-100 pl-3 dark:border-gray-800">
				<div class="h-[15.5rem] w-11 overflow-y-auto scrollbar-hidden" bind:this={hourList}>
					{#each HOURS as n}
						<button
							type="button"
							data-active={n === draftHour}
							class="w-full rounded-lg py-1 text-center tabular-nums transition {timeClass(
								n === draftHour
							)}"
							on:click={() => (draftHour = n)}
						>
							{pad(n)}
						</button>
					{/each}
				</div>
				<div class="h-[15.5rem] w-11 overflow-y-auto scrollbar-hidden" bind:this={minuteList}>
					{#each MINUTES as n}
						<button
							type="button"
							data-active={n === draftMinute}
							class="w-full rounded-lg py-1 text-center tabular-nums transition {timeClass(
								n === draftMinute
							)}"
							on:click={() => (draftMinute = n)}
						>
							{pad(n)}
						</button>
					{/each}
				</div>
			</div>
		</div>

		<div
			class="mt-3 flex items-center justify-between border-t border-gray-100 pt-3 dark:border-gray-800"
		>
			<div class="text-xs text-gray-500 dark:text-gray-400">
				{draftDate
					? formatDateTimeInput(`${draftDate}T${pad(draftHour)}:${pad(draftMinute)}`)
					: hint}
			</div>
			<div class="flex gap-2">
				{#if !required && value}
					<button
						type="button"
						class="rounded-full px-3 py-1.5 text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
						on:click={clear}
					>
						{$i18n.t('Clear')}
					</button>
				{/if}
				<button
					type="button"
					class="rounded-full bg-black px-4 py-1.5 text-white transition disabled:opacity-40 dark:bg-gray-100 dark:text-gray-900"
					disabled={!draftDate}
					on:click={confirm}
				>
					{$i18n.t('Confirm')}
				</button>
			</div>
		</div>
	</div>
{/if}
