<script lang="ts">
	// @ts-nocheck
	import { getContext, onDestroy, onMount } from 'svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SidebarIcon from '$lib/components/icons/Sidebar.svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import {
		chats,
		educationNotificationSummary,
		folders,
		mobile,
		pinnedChats,
		selectedFolder,
		showSidebar,
		user
	} from '$lib/stores';

	import {
		createPersonalWriting,
		deletePersonalWriting,
		getMyClassroom,
		getWritingHome,
		joinClassroom
	} from '$lib/apis/education';
	import { getClassroomDisplayName } from '$lib/utils/education';
	import LoadingState from '$lib/components/education/LoadingState.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import EduBadge from '$lib/components/education/EduBadge.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import { EDU_FIELD_CLASS, eduSegmentClass } from '$lib/components/education/styles';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let home = null;
	let loadError = '';
	let loaded = false;
	let inviteCode = '';
	let joining = false;
	let creatingPersonal = false;
	let activeTab = 'personal';
	let deletingPersonalIds = new Set<string>();
	let homeLoading = false;
	let pendingDeleteSessionId = '';
	let showDeleteConfirm = false;
	let unsubscribeNotifications;
	let notificationsInitialized = false;

	const DAY_SECONDS = 24 * 60 * 60;

	const getAssignmentStatusLabel = (status: string) => {
		if (status === 'submitted') return t('Submitted');
		if (status === 'draft') return t('In progress');
		if (status === 'not_started') return t('Not started');
		return t('Unknown');
	};

	const formatTimestamp = (timestamp?: number | null) => {
		if (typeof timestamp !== 'number' || !Number.isFinite(timestamp) || timestamp <= 0) {
			return t('Unknown');
		}

		const date = new Date(timestamp * 1000);
		if (Number.isNaN(date.getTime())) {
			return t('Unknown');
		}

		return date.toLocaleString();
	};

	// Returns due-date display info for a non-returned assignment card, or null when
	// there is nothing to show (e.g. no effective_due_at).
	const getDueInfo = (item) => {
		if (item.review_status === 'returned') {
			return null;
		}
		if (
			typeof item.effective_due_at !== 'number' ||
			!Number.isFinite(item.effective_due_at) ||
			item.effective_due_at <= 0
		) {
			return null;
		}

		const remainingSeconds = item.effective_due_at - Date.now() / 1000;
		const isUnsubmitted = item.status !== 'submitted';

		if (isUnsubmitted && remainingSeconds <= 0) {
			return { overdue: true, className: 'text-gray-500' };
		}

		if (isUnsubmitted && remainingSeconds < DAY_SECONDS) {
			return {
				overdue: false,
				className: 'font-medium text-amber-600',
				text: formatTimestamp(item.effective_due_at)
			};
		}

		return {
			overdue: false,
			className: 'text-gray-500',
			text: formatTimestamp(item.effective_due_at)
		};
	};

	// Not-yet-submitted assignments float to the top, ordered by the soonest effective
	// due date first (items without a due date sort to the end of that group).
	// Already submitted/graded assignments keep the existing "most recently updated first" order.
	const sortAssignmentItems = (items) => {
		const pending = [];
		const settled = [];
		for (const item of items ?? []) {
			if (item.status === 'submitted') {
				settled.push(item);
			} else {
				pending.push(item);
			}
		}

		pending.sort((a, b) => {
			const aDue = typeof a.effective_due_at === 'number' ? a.effective_due_at : null;
			const bDue = typeof b.effective_due_at === 'number' ? b.effective_due_at : null;
			if (aDue === null && bDue === null) return 0;
			if (aDue === null) return 1;
			if (bDue === null) return -1;
			return aDue - bDue;
		});

		settled.sort((a, b) => (b.updated_at ?? 0) - (a.updated_at ?? 0));

		return [...pending, ...settled];
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
			toast.error(`${error?.detail ?? error}`);
		} finally {
			creatingPersonal = false;
		}
	};

	const isPersonalWritingAlreadyDeleted = (error: unknown) => {
		return error?.status === 404 || error?.detail === 'Writing session not found';
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

		const deletedItem = (home?.personal_items ?? []).find((item) => item.writing_session.id === sessionId);
		const deletedProjectId = deletedItem?.project_id ?? null;

		deletingPersonalIds = new Set(deletingPersonalIds).add(sessionId);
		let deleteResult = null;
		try {
			deleteResult = await deletePersonalWriting(localStorage.token, sessionId);
		} catch (error) {
			if (!isPersonalWritingAlreadyDeleted(error)) {
				toast.error(`${error?.detail ?? error}`);
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
			recent_items: (home?.recent_items ?? []).filter((item) => item.writing_session_id !== sessionId)
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
			chats.update((items) =>
				(items ?? []).filter(
					(chat) => !deletedFolderIds.has(chat?.folder_id) && !deletedChatIds.has(chat?.id)
				)
			);
			pinnedChats.update((items) =>
				(items ?? []).filter(
					(chat) => !deletedFolderIds.has(chat?.folder_id) && !deletedChatIds.has(chat?.id)
				)
			);
			if (deletedFolderIds.has(get(selectedFolder)?.id)) {
				selectedFolder.set(null);
			}
		} else if (deletedChatIds.size > 0) {
			chats.update((items) => (items ?? []).filter((chat) => !deletedChatIds.has(chat?.id)));
			pinnedChats.update((items) => (items ?? []).filter((chat) => !deletedChatIds.has(chat?.id)));
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
			toast.error(`${error?.detail ?? error}`);
		} finally {
			joining = false;
		}
	};

	// Fetch-only: refreshes `home` (plus the classroom fallback) without touching
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
			if (!data?.classroom && role === 'student') {
				try {
					const classroomResponse = await getMyClassroom(localStorage.token);
					data.classroom = classroomResponse.classroom;
				} catch {}
			}
			home = data;
			return { role };
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
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
			const hasPendingAssignments = (home?.assignment_items ?? []).some(
				(item) => item.status !== 'submitted'
			);
			activeTab = hasPendingAssignments ? 'assignment' : 'personal';
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

	$: sortedAssignmentItems = sortAssignmentItems(home?.assignment_items ?? []);
</script>

{#if loaded && !loadError}
	<div
		class="flex h-screen max-h-[100dvh] w-full max-w-full flex-col transition-width duration-200 ease-in-out {$showSidebar
			? 'md:max-w-[calc(100%-var(--sidebar-width))]'
			: ''}"
	>
		<nav class="w-full px-2.5 pt-1.5 backdrop-blur-xl drag-region">
			<div class="flex items-center">
				{#if $mobile}
					<div class="{$showSidebar ? 'md:hidden' : ''} flex flex-none items-center self-end mt-1.5">
						<Tooltip
							content={$showSidebar ? $i18n.t('Close Sidebar') : $i18n.t('Open Sidebar')}
							interactive={true}
						>
							<button
								id="sidebar-toggle-button"
								class="flex cursor-pointer rounded-lg transition hover:bg-gray-100 dark:hover:bg-gray-850"
								on:click={() => showSidebar.set(!$showSidebar)}
							>
								<div class="self-center p-1.5">
									<SidebarIcon />
								</div>
							</button>
						</Tooltip>
					</div>
				{/if}

				<div class="ml-2 flex w-full items-center justify-between py-1">
					<div>
						<div class="text-xs uppercase tracking-[0.2em] text-gray-500">{$i18n.t('Writing')}</div>
						<h1 class="text-2xl font-semibold">{$i18n.t('Writing')}</h1>
					</div>
				</div>
			</div>
		</nav>

		<div class="flex-1 overflow-y-auto">
			<div class="mx-auto max-w-6xl px-4 py-8">
				<EduCard class="mb-8">
					<div class="mb-4 flex items-center justify-between gap-4">
						<div>
							<div class="text-lg font-semibold">{$i18n.t('Continue Recent Writing')}</div>
							<div class="text-sm text-gray-500">{$i18n.t('Jump back into your latest draft.')}</div>
						</div>
					</div>

					{#if (home?.recent_items ?? []).length === 0}
						<div class="rounded-2xl border border-dashed border-gray-200 bg-stone-50 p-5 text-sm text-gray-500">
							{$i18n.t('No recent writing yet.')}
						</div>
					{:else}
						<div class="grid gap-3 md:grid-cols-2">
							{#each home.recent_items as item}
								<button
									class="rounded-3xl border border-gray-200 bg-stone-50 p-4 text-left transition hover:border-gray-300 hover:bg-white"
									on:click={() => openRecentItem(item)}
								>
									<div class="flex items-center justify-between gap-3">
										<div class="text-sm font-semibold text-gray-900">{item.title}</div>
										<EduBadge soft>
											{item.project_mode === 'assignment_writing'
												? $i18n.t('Assignment Writing')
												: $i18n.t('Personal Writing')}
										</EduBadge>
									</div>
									<div class="mt-2 text-xs text-gray-500">
										{$i18n.t('Updated')}: {formatTimestamp(item.updated_at)}
									</div>
								</button>
							{/each}
						</div>
					{/if}
				</EduCard>

				{#if ($user?.education_role || home?.role) === 'student'}
					<div class="mb-5 flex gap-2">
						<button
							class={eduSegmentClass(activeTab === 'assignment')}
							on:click={() => (activeTab = 'assignment')}
						>
							{$i18n.t('Assignment Writing')}
						</button>
						<button
							class={eduSegmentClass(activeTab === 'personal')}
							on:click={() => (activeTab = 'personal')}
						>
							{$i18n.t('Personal Writing')}
						</button>
					</div>

					{#if activeTab === 'assignment'}
						<div class="mb-8">
							<EduCard class="mb-6">
								<div class="mb-3 text-sm font-semibold">{$i18n.t('My Classroom')}</div>
								{#if home?.classroom}
									<div class="text-sm text-gray-600">
										{$i18n.t('You are connected to {{name}}.', {
											name: getClassroomDisplayName(home.classroom.name, t)
										})}
									</div>
								{:else}
									<div class="text-sm text-gray-500">
										{$i18n.t(
											"You have not joined a classroom yet. Enter your teacher's invite code to unlock assignments."
										)}
									</div>
									<div class="mt-4 flex flex-col gap-3 md:flex-row">
										<input
											bind:value={inviteCode}
											class="flex-1 {EDU_FIELD_CLASS}"
											placeholder={$i18n.t('Enter classroom invite code')}
										/>
										<EduButton variant="primary" on:click={joinCurrentClassroom} disabled={joining}>
											{joining ? $i18n.t('Joining...') : $i18n.t('Join Classroom')}
										</EduButton>
									</div>
								{/if}
							</EduCard>

							<div class="mb-4">
								<div class="text-lg font-semibold">{$i18n.t('Pending Assignments')}</div>
							</div>

							{#if sortedAssignmentItems.length === 0}
								<EduStateCard>{$i18n.t('No assignments available yet.')}</EduStateCard>
							{:else}
								<div class="grid gap-4">
									{#each sortedAssignmentItems as item}
										<EduCard>
											<div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
												<div>
													<div class="flex flex-wrap items-center gap-2">
														<div class="text-lg font-semibold">{item.assignment.title}</div>
														{#if item.review_status === 'returned'}
															<EduBadge soft tone="rose">{$i18n.t('Returned')}</EduBadge>
														{:else if item.review_status === 'reviewed'}
															<EduBadge soft tone="emerald">
																{$i18n.t('Reviewed')} {item.score ?? ''}
															</EduBadge>
														{:else if item.review_status === 'pending'}
															<EduBadge soft>{$i18n.t('Awaiting review')}</EduBadge>
														{/if}
													</div>
													<div class="mt-1 text-sm text-gray-500">
														{item.assignment.description || $i18n.t('No description')}
													</div>
													<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
														<div>{$i18n.t('Status')}: {getAssignmentStatusLabel(item.status)}</div>
														<div>{$i18n.t('Updated')}: {formatTimestamp(item.updated_at)}</div>
														{#if item.review_status === 'returned'}
															<div class="font-medium text-rose-600">
																{$i18n.t('Resubmit before')}: {formatTimestamp(item.effective_due_at)}
															</div>
														{:else}
															{@const dueInfo = getDueInfo(item)}
															{#if dueInfo?.overdue}
																<div class={dueInfo.className}>{$i18n.t('Overdue')}</div>
															{:else if dueInfo}
																<div class={dueInfo.className}>
																	{$i18n.t('Due At')}: {dueInfo.text}
																</div>
															{/if}
														{/if}
													</div>
												</div>

												<EduButton
													variant="primary"
													on:click={() => goto(`/assignments/${item.assignment.id}/write`)}
												>
													{$i18n.t('Open Assignment')}
												</EduButton>
											</div>
										</EduCard>
									{/each}
								</div>
							{/if}
						</div>
					{/if}
				{/if}

				{#if ($user?.education_role || home?.role) !== 'student' || activeTab === 'personal'}
					<div>
						<div class="mb-4 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
							<div class="text-lg font-semibold">{$i18n.t('My Writing')}</div>
							<EduButton
								variant="primary"
								class="w-full md:w-auto"
								on:click={startPersonalWriting}
								disabled={creatingPersonal}
							>
								{creatingPersonal ? $i18n.t('Creating...') : $i18n.t('New Writing')}
							</EduButton>
						</div>
						<div class="mb-4 text-sm text-gray-500">{$i18n.t('Your personal drafts live here.')}</div>

						{#if (home?.personal_items ?? []).length === 0}
							<EduStateCard>{$i18n.t('No personal writing yet.')}</EduStateCard>
						{:else}
							<div class="grid gap-4">
								{#each home.personal_items as item}
									<EduCard>
										<div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
											<div class="min-w-0">
												<div class="truncate text-lg font-semibold">{item.title}</div>
												<div class="mt-1 text-sm text-gray-500">
													{item.preview_text || $i18n.t('No content yet.')}
												</div>
												<div class="mt-3 text-xs text-gray-500">
													{$i18n.t('Updated')}: {formatTimestamp(item.updated_at)}
												</div>
											</div>
											<div class="flex gap-2">
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
					</div>
				{/if}
			</div>
		</div>
	</div>
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
