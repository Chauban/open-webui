<script lang="ts">
	// 后端 difflib opcodes 渲染成行内对比:新增标绿,删除标红划线。
	// 「与上一轮对比」和「初稿 → 终稿」共用。
	export let blocks: Array<{ op: string; old_text: string; new_text: string }> = [];
</script>

<div
	class="mt-2 p-3 rounded-lg border border-gray-200 dark:border-gray-800 text-sm leading-7 whitespace-pre-wrap"
>
	{#each blocks as block}
		{#if block.op === 'equal'}<span>{block.new_text}</span>
		{:else if block.op === 'insert'}<span class="bg-emerald-100 dark:bg-emerald-900/50"
				>{block.new_text}</span
			>
		{:else if block.op === 'delete'}<span class="bg-rose-100 dark:bg-rose-900/50 line-through"
				>{block.old_text}</span
			>
		{:else}<span class="bg-rose-100 dark:bg-rose-900/50 line-through">{block.old_text}</span><span
				class="bg-emerald-100 dark:bg-emerald-900/50">{block.new_text}</span
			>{/if}
	{/each}
</div>
