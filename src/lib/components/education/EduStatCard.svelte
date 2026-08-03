<script lang="ts">
	import { getContext } from 'svelte';
	import EduCard from './EduCard.svelte';

	// 看板统计卡：小标题 + 大数字。此前在 4 个页面里逐字重复，
	// 每处自己拼 uppercase tracking 与配色。
	export let label = '';
	export let value: string | number = 0;
	export let tone: 'default' | 'rose' | 'amber' | 'sky' = 'default';

	const i18n = getContext('i18n');

	const LABEL_TONES = {
		default: 'text-gray-500',
		rose: 'text-rose-600',
		amber: 'text-amber-600',
		sky: 'text-sky-600'
	};
	const VALUE_TONES = {
		default: '',
		rose: 'text-rose-700',
		amber: 'text-amber-700',
		sky: 'text-sky-700'
	};

	// 统计卡的底色跟随语义色，default 用普通白卡。
	$: cardTone = tone === 'default' ? 'default' : tone;
</script>

<EduCard tone={cardTone}>
	<div class="text-xs uppercase tracking-[0.16em] {LABEL_TONES[tone]}">{$i18n.t(label)}</div>
	<div class="mt-2 text-3xl font-semibold {VALUE_TONES[tone]}">{value}</div>
</EduCard>
