<script lang="ts">
	import { page } from '$app/stores';
	import WritingWorkspaceShell from '$lib/components/education/WritingWorkspaceShell.svelte';
	import {
		getAssignmentWorkspace,
		getEducationNotificationSummary,
		markEducationNotificationsRead
	} from '$lib/apis/education';
	import { educationNotificationSummary } from '$lib/stores';

	const loadWorkspace = async () => {
		const workspace = await getAssignmentWorkspace(localStorage.token, $page.params.assignmentId);

		try {
			await markEducationNotificationsRead(localStorage.token, {
				assignment_id: $page.params.assignmentId,
				types: [
					'assignment_published',
					'assignment_updated',
					'assignment_reminder',
					'review_completed',
					'submission_returned'
				]
			});
			educationNotificationSummary.set(
				await getEducationNotificationSummary(localStorage.token).catch(() => null)
			);
		} catch (e) {
			console.error('Failed to mark education notifications as read:', e);
		}

		return workspace;
	};
</script>

<WritingWorkspaceShell
	scope="assignment"
	projectBaseUrl={`/assignments/${$page.params.assignmentId}/write`}
	{loadWorkspace}
/>
