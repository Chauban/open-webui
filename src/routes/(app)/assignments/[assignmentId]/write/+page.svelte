<script lang="ts">
	import { page } from '$app/stores';
	import WritingWorkspaceShell from '$lib/components/education/WritingWorkspaceShell.svelte';
	import { getAssignmentWorkspace } from '$lib/apis/education';

	const loadWorkspace = () => getAssignmentWorkspace(localStorage.token, $page.params.assignmentId);
</script>

<WritingWorkspaceShell
	scope="assignment"
	projectBaseUrl={`/assignments/${$page.params.assignmentId}/write`}
	{loadWorkspace}
/>
