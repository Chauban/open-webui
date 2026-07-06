<script lang="ts">
	import { page } from '$app/stores';
	import WritingWorkspaceShell from '$lib/components/education/WritingWorkspaceShell.svelte';
	import { getWritingWorkspace } from '$lib/apis/education';

	const loadWorkspace = () => getWritingWorkspace(localStorage.token, $page.params.sessionId);
</script>

<WritingWorkspaceShell
	scope="personal"
	projectBaseUrl={`/writing/${$page.params.sessionId}`}
	{loadWorkspace}
/>
