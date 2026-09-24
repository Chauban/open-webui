<script lang="ts">
	import { getContext } from 'svelte';
	import { page } from '$app/stores';

	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import SubmissionQueue from '$lib/components/education/SubmissionQueue.svelte';

	const i18n = getContext('i18n');

	// 总览、班级页的统计卡带着 ?status= / ?classroom= 跳进来,直接落到筛好的队列。
	const QUEUE_STATUSES = ['pending', 'returned', 'reviewed', 'all'];
	const params = $page.url.searchParams;
	let status = QUEUE_STATUSES.includes(params.get('status') ?? '')
		? (params.get('status') as 'pending' | 'returned' | 'reviewed' | 'all')
		: 'pending';
</script>

<TeacherPageShell title={$i18n.t('Review')}>
	<div class="mx-auto max-w-6xl px-4 py-6">
		<SubmissionQueue
			bind:status
			initialClassroomId={params.get('classroom') ?? ''}
			initialAssignmentId={params.get('assignment') ?? ''}
		/>
	</div>
</TeacherPageShell>
