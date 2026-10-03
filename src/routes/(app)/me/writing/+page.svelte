<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext, onDestroy, onMount } from 'svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import {
		educationNotificationSummary,
		folders,
		selectedFolder,
		user
	} from '$lib/stores';
	import { refreshChatList } from '$lib/stores/chatList';

	import {
		createPersonalWriting,
		deletePersonalWriting,
		getWritingHome,
		joinClassroom
	} from '$lib/apis/education';
	import {
		formatEpoch,
		getClassroomDisplayName,
		getDueCountdown,
		resolveErrorMessage
	} from '$lib/utils/education';
	import LoadingState from '$lib/components/education/LoadingState.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import EduBadge from '$lib/components/education/EduBadge.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import EduPageShell from '$lib/components/education/EduPageShell.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte';
	import { EDU_FIELD_CLASS, eduSegmentClass } from '$lib/components/education/styles';

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let home = null;
	let loadError = '';
	let loaded = false;
	let inviteCode = '';
	let joining = false;
	let creatingPersonal = false;
	let activeTab = 'personal';
	let showDone = false;
	let showMissed = false;
	let deletingPersonalIds = new Set<string>();
	let homeLoading = false;
	let pendingDeleteSessionId = '';
	let showDeleteConfirm = false;
	let unsubscribeNotifications;
	let notificationsInitialized = false;

	const formatTimestamp = (timestamp?: number | null) =>
		typeof timestamp === 'number' && timestamp > 0 ? formatEpoch(timestamp) : t('Unknown');

	const isPastEffectiveDue = (item) =>
		typeof item.effective_due_at === 'number' &&
		item.effective_due_at > 0 &&
		item.effective_due_at <= Date.now() / 1000;

	// 退回的作业要学生动手,和没交的一起算「待完成」;其余已提交的收进下方折叠区。
	const needsAction = (item) => item.status !== 'submitted' || item.review_status === 'returned';

	// 待完成:还能交的,截止最近的在前(没有截止的垫底);
	// 已截止未交:过了截止交不了了,只剩回看,收进折叠区,截止最近的在前——
	// 混在待完成里会排在最前头,把真正要做的作业挤到下面去;
	// 已提交:最近更新的在前。
	const groupAssignmentItems = (items) => {
		const todo = [];
		const missed = [];
		const done = [];
		for (const item of items ?? []) {
			if (!needsAction(item)) done.push(item);
			else if (isPastEffectiveDue(item)) missed.push(item);
			else todo.push(item);
		}
		todo.sort((a, b) => (a.effective_due_at ?? Infinity) - (b.effective_due_at ?? Infinity));
		missed.sort((a, b) => (b.effective_due_at ?? 0) - (a.effective_due_at ?? 0));
		done.sort((a, b) => (b.updated_at ?? 0) - (a.updated_at ?? 0));
		return { todo, missed, done };
	};

	// 卡片右侧的按钮按状态说清楚下一步,而不是一律「打开作业」。
	const getAssignmentAction = (item) => {
		if (item.review_status === 'returned') return { label: 'Revise and Resubmit', primary: true };
		if (item.status === 'not_started') return { label: 'Start Writing', primary: true };
		if (item.status !== 'submitted') return { label: 'Continue Writing', primary: true };
		if (item.review_status === 'reviewed') return { label: 'View Review', primary: false };
		return { label: 'View Submission', primary: false };
	};

	const openRecentItem = async (item) => {
		if (item.project_mode === 'assignment_writing' && item.assignment?.id) {
			await goto(`/assignments/${item.assignment.id}/write`);
			return;
		}
		await goto(`/writing/${item.writing_session_id}`);
	};

	const startPersonalWriting = async () => {
		creatingPersonal = true;
		try {
			const workspace = await createPersonalWriting(localStorage.token, {
				title: t('Untitled Writing')
			});
			await goto(`/writing/${workspace.writing_session.id}`);
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			creatingPersonal = false;
		}
	};

	const isPersonalWritingAlreadyDeleted = (error: unknown) => {
		const { status, detail } = (error ?? {}) as { status?: number; detail?: unknown };
		return status === 404 || detail === 'Writing session not found';
	};

	// 删除会连带清掉对应的项目文件夹与对话，且不可撤销，所以先确认。
	const requestRemovePersonalWriting = (sessionId: string) => {
		pendingDeleteSessionId = sessionId;
		showDeleteConfirm = true;
	};

	const confirmRemovePersonalWriting = async () => {
		const sessionId = pendingDeleteSessionId;
		pendingDeleteSessionId = '';
		if (sessionId) {
			await removePersonalWriting(sessionId);
		}
	};

	const removePersonalWriting = async (sessionId: string) => {
		if (deletingPersonalIds.has(sessionId)) {
			return;
		}

		const deletedItem = (home?.personal_items ?? []).find(
			(item) => item.writing_session.id === sessionId
		);
		const deletedProjectId = deletedItem?.project_id ?? null;

		deletingPersonalIds = new Set(deletingPersonalIds).add(sessionId);
		let deleteResult = null;
		try {
			deleteResult = await deletePersonalWriting(localStorage.token, sessionId);
		} catch (error) {
			if (!isPersonalWritingAlreadyDeleted(error)) {
				toast.error(resolveErrorMessage(error, t));
				return;
			}
		} finally {
			const nextDeletingIds = new Set(deletingPersonalIds);
			nextDeletingIds.delete(sessionId);
			deletingPersonalIds = nextDeletingIds;
		}

		home = {
			...home,
			personal_items: (home?.personal_items ?? []).filter(
				(item) => item.writing_session.id !== sessionId
			),
			recent_items: (home?.recent_items ?? []).filter(
				(item) => item.writing_session_id !== sessionId
			)
		};

		const deletedFolderIds = new Set([
			...(deleteResult?.deleted_folder_ids ?? []),
			...(deletedProjectId ? [deletedProjectId] : [])
		]);
		const deletedChatIds = new Set(deleteResult?.deleted_chat_ids ?? []);

		if (deletedFolderIds.size > 0) {
			folders.update((items) =>
				(items ?? []).filter((folder) => !deletedFolderIds.has(folder?.id))
			);
			if (deletedFolderIds.has(get(selectedFolder)?.id)) {
				selectedFolder.set(null);
			}
		}
		// 对话列表 store 自 0.11 起是只读的，只能整页重拉；置顶里的对话也可能被一并删掉。
		if (deletedFolderIds.size > 0 || deletedChatIds.size > 0) {
			await refreshChatList(localStorage.token, { refreshPinned: true });
		}

		toast.success(t('Deleted'));
	};

	const joinCurrentClassroom = async () => {
		if (!inviteCode.trim()) {
			toast.error(t('Classroom invite code is required.'));
			return;
		}

		joining = true;
		try {
			await joinClassroom(localStorage.token, { invite_code: inviteCode.trim() });
			inviteCode = '';
			await loadData();
			toast.success(t('Joined classroom.'));
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			joining = false;
		}
	};

	// Fetch-only: refreshes `home` without touching
	// `activeTab`, so background refreshes never yank the user off their current tab.
	const fetchHomeData = async () => {
		if (homeLoading) {
			return null;
		}
		homeLoading = true;
		loadError = '';
		try {
			const data = await getWritingHome(localStorage.token);
			const sessionUser = get(user);
			const role = sessionUser?.education_role || data?.role;
			home = data;
			return { role };
		} catch (error) {
			loadError = resolveErrorMessage(error, t);
			toast.error(loadError);
			return null;
		} finally {
			homeLoading = false;
		}
	};

	// Full load: fetches home data and (re)derives the default active tab. Used for the
	// initial mount and for user-triggered reloads (e.g. after joining a classroom).
	const loadData = async () => {
		const result = await fetchHomeData();
		if (!result) {
			return;
		}
		const { role } = result;
		if (role === 'student') {
			const hasPendingAssignments =
				groupAssignmentItems(home?.assignment_items).todo.length > 0;
			// 还没加入班级的学生要先落在作业页，邀请码入口就在这一屏。
			const hasClassroom = (home?.classrooms ?? []).length > 0;
			activeTab = hasPendingAssignments || !hasClassroom ? 'assignment' : 'personal';
		} else {
			activeTab = 'personal';
		}
	};

	onMount(async () => {
		await loadData();
		loaded = true;

		// Refresh the homepage whenever a new education notification arrives (new
		// assignment published, review completed/returned, etc.) so students who are
		// sitting on this page see updates without reloading. Uses the fetch-only helper
		// so a background refresh never changes which tab the user is currently viewing.
		// Skip the initial value the subscription fires with on subscribe — that's just
		// this mount's own state, not a new notification.
		unsubscribeNotifications = educationNotificationSummary.subscribe(() => {
			if (!notificationsInitialized) {
				notificationsInitialized = true;
				return;
			}
			fetchHomeData();
		});
	});

	onDestroy(() => {
		unsubscribeNotifications?.();
	});

	$: assignmentGroups = groupAssignmentItems(home?.assignment_items ?? []);
	$: isStudent = ($user?.education_role || home?.role) === 'student';
	// 首页顶部只留一条「接着写」:最近一份还没交的草稿。已交的不在这里重复出现。
	$: resumeItem = (home?.recent_items ?? []).find((item) => item.status !== 'submitted') ?? null;
</script>

{#if loaded && !loadError}
	<!--
		此前首页最上面是 12 张「最近写作」卡片,把待完成作业挤出第一屏,
		而它们与下面两个列表几乎全部重复。现在顶部只留一条「接着写」,
		作业分「待完成 / 已提交」两组,已提交的默认折叠。
	-->
	<EduPageShell title={$i18n.t('Writing')}>
		<svelte:fragment slot="nav-actions">
			<EduButton on:click={() => goto('/me/writing/growth')}>
				{$i18n.t('My Growth')}
			</EduButton>
		</svelte:fragment>

		<div class="mx-auto max-w-6xl px-4 py-6">
			{#if resumeItem}
				<button
					class="mb-6 flex w-full items-center gap-4 rounded-2xl border border-gray-200 bg-white px-5 py-4 text-left transition hover:border-gray-300 hover:shadow-sm dark:border-gray-800 dark:bg-gray-850 dark:hover:border-gray-700"
					on:click={() => openRecentItem(resumeItem)}
				>
					<div class="min-w-0 flex-1">
						<div class="text-xs text-gray-500 dark:text-gray-400">
							{$i18n.t('Pick up where you left off')} ·
							{resumeItem.project_mode === 'assignment_writing'
								? $i18n.t('Assignment Writing')
								: $i18n.t('Personal Writing')}
						</div>
						<div class="mt-0.5 truncate text-base font-semibold text-gray-900 dark:text-gray-100">
							{resumeItem.title}
						</div>
					</div>
					<div class="shrink-0 text-xs text-gray-500 dark:text-gray-400">
						{formatTimestamp(resumeItem.updated_at)}
					</div>
					<ChevronRight className="size-4 shrink-0 text-gray-400" />
				</button>
			{/if}

			{#if isStudent}
				<div class="mb-5 flex flex-wrap items-center justify-between gap-3">
					<div class="flex gap-2">
						<button
							class={eduSegmentClass(activeTab === 'assignment')}
							on:click={() => (activeTab = 'assignment')}
						>
							{$i18n.t('Assignment Writing')}
							{#if assignmentGroups.todo.length > 0}
								<span class="ml-1 tabular-nums opacity-70">{assignmentGroups.todo.length}</span>
							{/if}
						</button>
						<button
							class={eduSegmentClass(activeTab === 'personal')}
							on:click={() => (activeTab = 'personal')}
						>
							{$i18n.t('Personal Writing')}
						</button>
					</div>
					<!-- 入班后班级只是一条身份信息,不再单独占一张卡;换班规则放进悬停提示 -->
					{#if home?.classrooms?.length}
						<Tooltip
							content={$i18n.t(
								'Each student can be in only one classroom. To change classes, ask your teacher or an administrator.'
							)}
						>
							<div class="text-xs text-gray-500 dark:text-gray-400">
								{$i18n.t('My Classroom')}:
								<span class="font-medium text-gray-700 dark:text-gray-300">
									{getClassroomDisplayName(home.classrooms[0].name, t)}
								</span>
							</div>
						</Tooltip>
					{/if}
				</div>

				{#if activeTab === 'assignment'}
					{#if !home?.classrooms?.length}
						<EduCard class="mb-6">
							<div class="text-base font-semibold">{$i18n.t('Join Classroom')}</div>
							<div class="mt-1 text-sm text-gray-500 dark:text-gray-400">
								{$i18n.t(
									"You have not joined a classroom yet. Enter your teacher's invite code to unlock assignments."
								)}
							</div>
							<form
								class="mt-4 flex flex-col gap-3 md:flex-row"
								on:submit|preventDefault={joinCurrentClassroom}
							>
								<input
									bind:value={inviteCode}
									class="flex-1 font-mono {EDU_FIELD_CLASS}"
									placeholder={$i18n.t('Enter classroom invite code')}
								/>
								<EduButton variant="primary" type="submit" disabled={joining}>
									{joining ? $i18n.t('Joining...') : $i18n.t('Join Classroom')}
								</EduButton>
							</form>
						</EduCard>
					{/if}

					{#if (home?.assignment_items ?? []).length === 0}
						{#if home?.classrooms?.length}
							<EduStateCard>{$i18n.t('No assignments available yet.')}</EduStateCard>
						{/if}
					{:else}
						<h2 class="mb-3 text-base font-semibold">
							{$i18n.t('Pending Assignments')}
							<span class="ml-1 text-sm font-normal text-gray-500 tabular-nums dark:text-gray-400">
								{assignmentGroups.todo.length}
							</span>
						</h2>
						{#if assignmentGroups.todo.length === 0}
							<EduStateCard>{$i18n.t('All caught up. Nothing is waiting for you.')}</EduStateCard>
						{:else}
							<div class="grid gap-3">
								{#each assignmentGroups.todo as item (item.assignment.id)}
									{@render assignmentCard(item)}
								{/each}
							</div>
						{/if}

						{#if assignmentGroups.missed.length > 0}
							<button
								class="mt-8 mb-3 flex items-center gap-1.5 text-base font-semibold"
								aria-expanded={showMissed}
								on:click={() => (showMissed = !showMissed)}
							>
								<ChevronRight
									className="size-4 text-gray-400 transition-transform {showMissed
										? 'rotate-90'
										: ''}"
								/>
								{$i18n.t('Past due, not submitted')}
								<span class="text-sm font-normal text-gray-500 tabular-nums dark:text-gray-400">
									{assignmentGroups.missed.length}
								</span>
							</button>
							{#if showMissed}
								<div class="grid gap-3">
									{#each assignmentGroups.missed as item (item.assignment.id)}
										{@render assignmentCard(item)}
									{/each}
								</div>
							{/if}
						{/if}

						{#if assignmentGroups.done.length > 0}
							<button
								class="mt-8 mb-3 flex items-center gap-1.5 text-base font-semibold"
								aria-expanded={showDone}
								on:click={() => (showDone = !showDone)}
							>
								<ChevronRight
									className="size-4 text-gray-400 transition-transform {showDone
										? 'rotate-90'
										: ''}"
								/>
								{$i18n.t('Submitted')}
								<span class="text-sm font-normal text-gray-500 tabular-nums dark:text-gray-400">
									{assignmentGroups.done.length}
								</span>
							</button>
							{#if showDone}
								<div class="grid gap-3">
									{#each assignmentGroups.done as item (item.assignment.id)}
										{@render assignmentCard(item)}
									{/each}
								</div>
							{/if}
						{/if}
					{/if}
				{/if}
			{/if}

			{#if !isStudent || activeTab === 'personal'}
				<div class="mb-3 flex items-center justify-between gap-4">
					<div>
						<h2 class="text-base font-semibold">{$i18n.t('My Writing')}</h2>
						<div class="text-sm text-gray-500 dark:text-gray-400">
							{$i18n.t('Your personal drafts live here.')}
						</div>
					</div>
					<EduButton variant="primary" on:click={startPersonalWriting} disabled={creatingPersonal}>
						<Plus className="size-4" strokeWidth="2.5" />
						{creatingPersonal ? $i18n.t('Creating...') : $i18n.t('New Writing')}
					</EduButton>
				</div>

				{#if (home?.personal_items ?? []).length === 0}
					<EduStateCard>{$i18n.t('No personal writing yet.')}</EduStateCard>
				{:else}
					<div class="grid gap-3">
						{#each home.personal_items as item (item.writing_session.id)}
							<EduCard>
								<div class="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
									<div class="min-w-0">
										<div class="truncate text-base font-semibold">{item.title}</div>
										<div class="mt-1 line-clamp-2 text-sm text-gray-500 dark:text-gray-400">
											{item.preview_text || $i18n.t('No content yet.')}
										</div>
										<div class="mt-2 text-xs text-gray-500 dark:text-gray-400">
											{$i18n.t('Updated')}: {formatTimestamp(item.updated_at)}
										</div>
									</div>
									<div class="flex shrink-0 gap-2">
										<EduButton
											on:click={() => requestRemovePersonalWriting(item.writing_session.id)}
											disabled={deletingPersonalIds.has(item.writing_session.id)}
										>
											{deletingPersonalIds.has(item.writing_session.id)
												? $i18n.t('Deleting...')
												: $i18n.t('Delete')}
										</EduButton>
										<EduButton
											variant="primary"
											on:click={() => goto(`/writing/${item.writing_session.id}`)}
										>
											{$i18n.t('Continue Writing')}
										</EduButton>
									</div>
								</div>
							</EduCard>
						{/each}
					</div>
				{/if}
			{/if}
		</div>
	</EduPageShell>

	{#snippet assignmentCard(item)}
		{@const action = getAssignmentAction(item)}
		{@const countdown =
			item.effective_due_at && needsAction(item) ? getDueCountdown(item.effective_due_at) : null}
		<EduCard>
			<div class="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
				<div class="min-w-0">
					<div class="flex flex-wrap items-center gap-2">
						<div class="text-base font-semibold">{item.assignment.title}</div>
						<!-- 修订初稿要先交初稿才能开始，进门前就让学生知道；从零写作是常态，不标。 -->
						{#if item.assignment.task_mode === 'revise_draft'}
							<EduBadge soft>{$i18n.t('Revise a draft')}</EduBadge>
						{/if}
						{#if item.review_status === 'returned'}
							<EduBadge soft tone="rose">{$i18n.t('Returned')}</EduBadge>
						{:else if item.review_status === 'reviewed'}
							<EduBadge soft tone="emerald">
								{$i18n.t('Reviewed')}
								{item.score ?? ''}
							</EduBadge>
						{:else if item.review_status === 'pending'}
							<!-- 待批改且未过截止时学生仍可改稿重交(覆盖当前轮),标签要说清楚 -->
							<EduBadge soft>
								{isPastEffectiveDue(item)
									? $i18n.t('Awaiting review')
									: $i18n.t('Submitted · editable before deadline')}
							</EduBadge>
						{:else if item.status === 'draft'}
							<EduBadge soft tone="sky">{$i18n.t('In progress')}</EduBadge>
						{/if}
					</div>
					{#if item.assignment.description}
						<div class="mt-1 line-clamp-2 text-sm text-gray-500 dark:text-gray-400">
							{item.assignment.description}
						</div>
					{/if}
					{#if item.effective_due_at}
						<div class="mt-2 flex flex-wrap gap-x-3 text-xs text-gray-500 dark:text-gray-400">
							<span class={item.review_status === 'returned'
								? 'font-medium text-rose-600 dark:text-rose-400'
								: ''}
							>
								{item.review_status === 'returned'
									? $i18n.t('Resubmit before')
									: $i18n.t('Due At')}: {formatTimestamp(item.effective_due_at)}
							</span>
							{#if countdown}
								<span class={countdown.className}>
									{countdown.overdue
										? $i18n.t('Overdue')
										: $i18n.t(countdown.labelKey, countdown.params)}
								</span>
							{/if}
						</div>
					{/if}
				</div>

				<EduButton
					class="shrink-0"
					variant={action.primary ? 'primary' : 'secondary'}
					on:click={() => goto(`/assignments/${item.assignment.id}/write`)}
				>
					{$i18n.t(action.label)}
				</EduButton>
			</div>
		</EduCard>
	{/snippet}
{:else if loadError}
	<div class="mx-auto max-w-3xl px-4 py-16">
		<EduStateCard tone="error">{loadError}</EduStateCard>
	</div>
{:else}
	<LoadingState messageKey="Loading writing home..." />
{/if}

<ConfirmDialog
	bind:show={showDeleteConfirm}
	title={$i18n.t('Delete Personal Writing')}
	message={$i18n.t(
		'Delete this personal writing? Its project folder and chats are removed as well, and this cannot be undone.'
	)}
	on:confirm={confirmRemovePersonalWriting}
/>
