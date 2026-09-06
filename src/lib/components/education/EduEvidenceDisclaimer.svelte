<script lang="ts">
	import { getContext } from 'svelte';
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte';

	// 来源占比和风险提示都建立在客户端上报之上:学生端记录、学生端提交,答案侧和
	// source map 同一信任层级(见 AGENTS.md 的留痕口径)。教师界面把「AI pasted 42%」
	// 当事实陈述展示,最坏的结果不是数字被伪造,而是教师据此对学生提出学术不端指控。
	// 加固成本远高于收益且已定案不做,那么口径就必须写在数字旁边,而不是留在文档里。
	const i18n = getContext('i18n');

	let className = '';
	export { className as class };
</script>

<div
	class="flex items-start gap-1.5 text-xs leading-relaxed text-gray-500 dark:text-gray-400 {className}"
>
	<div class="mt-0.5 shrink-0">
		<InfoCircle className="size-3.5" />
	</div>
	<div>
		{$i18n.t(
			'Recorded by the student browser while writing, so it can be incomplete or bypassed. Use it to talk through the writing process, not as proof of academic misconduct.'
		)}
	</div>
</div>
