<script lang="ts">
	import { page } from '$app/stores';
	import { onDestroy } from 'svelte';
	import { workspaceBackground } from '$lib/utils/workspace-background';
	import WritingWorkspaceShell from '$lib/components/education/WritingWorkspaceShell.svelte';
	import {
		getAssignmentWorkspace,
		getEducationNotificationSummary,
		markEducationNotificationsRead
	} from '$lib/apis/education';
	import { educationNotificationSummary } from '$lib/stores';
	let generation = 0;
	let disposed = false;
	onDestroy(() => {
		disposed = true;
		generation++;
	});

	const refreshNotifications = async (token: string, assignmentId: string, request: number) => {
		const current = () =>
			!disposed &&
			request === generation &&
			token === localStorage.token &&
			assignmentId === $page.params.assignmentId;
		try {
			await markEducationNotificationsRead(token, {
				assignment_id: assignmentId,
				types: [
					'assignment_published',
					'assignment_updated',
					'assignment_reminder',
					'review_completed',
					'submission_returned'
				]
			});
			if (!current()) return;
			const summary = await getEducationNotificationSummary(token);
			if (current()) educationNotificationSummary.set(summary);
		} catch (e) {
			console.error('Failed to mark education notifications as read:', e);
		}
	};

	const loadWorkspace = async () => {
		const request = ++generation;
		const token = localStorage.token;
		const assignmentId = $page.params.assignmentId;
		const workspace = await getAssignmentWorkspace(token, assignmentId);
		// 通知已读和角标更新不阻塞稿件、阅读状态及历史对话恢复。
		if (
			!disposed &&
			request === generation &&
			token === localStorage.token &&
			assignmentId === $page.params.assignmentId
		)
			void workspaceBackground(
				`notifications:${token}:${assignmentId}`,
				() => refreshNotifications(token, assignmentId, request),
				() => !disposed && request === generation && token === localStorage.token
			);
		return workspace;
	};
</script>

<!-- SvelteKit 复用同一路由的页面组件,不加 key 时切换作业不会重新挂载工作区 -->
{#key $page.params.assignmentId}
	<WritingWorkspaceShell
		scope="assignment"
		projectBaseUrl={`/assignments/${$page.params.assignmentId}/write`}
		{loadWorkspace}
	/>
{/key}
