<script lang="ts">
	// 卡片内部的虚线空态占位（「暂无待批改提交」等），9 处逐字重复。
	let className = '';
	export { className as class };
</script>

<div
	class="rounded-2xl border border-dashed border-gray-300 px-4 py-5 text-sm text-gray-500 {className}"
>
	<slot />
</div>
