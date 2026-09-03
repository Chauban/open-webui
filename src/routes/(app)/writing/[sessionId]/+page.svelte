<script lang="ts">
	import { page } from '$app/stores';
	import WritingWorkspaceShell from '$lib/components/education/WritingWorkspaceShell.svelte';
	import { getWritingWorkspace } from '$lib/apis/education';

	const loadWorkspace = () => getWritingWorkspace(localStorage.token, $page.params.sessionId);
</script>

<!-- SvelteKit 复用同一路由的页面组件,不加 key 时切换写作项目不会重新挂载工作区 -->
{#key $page.params.sessionId}
	<WritingWorkspaceShell
		scope="personal"
		projectBaseUrl={`/writing/${$page.params.sessionId}`}
		{loadWorkspace}
	/>
{/key}
