<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SidebarIcon from '$lib/components/icons/Sidebar.svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import {
		chats,
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

	const LEGACY_DEFAULT_CLASSROOM_NAMES = new Set(['Default Classroom', '默认班级']);
	const getClassroomNameForDisplay = (name: string) => {
		const normalizedName = name?.trim();
		return LEGACY_DEFAULT_CLASSROOM_NAMES.has(normalizedName) ? t('Default Classroom') : name;
	};

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

	const loadData = async () => {
		loadError = '';
		try {
			home = await getWritingHome(localStorage.token);
			const sessionUser = get(user);
			const role = sessionUser?.education_role || home?.role;
			if (role === 'student') {
				const hasPendingAssignments = (home?.assignment_items ?? []).some(
					(item) => item.status !== 'submitted'
				);
				activeTab = hasPendingAssignments ? 'assignment' : 'personal';
			} else {
				activeTab = 'personal';
			}
			if (!home?.classroom && role === 'student') {
				try {
					const classroomResponse = await getMyClassroom(localStorage.token);
					home.classroom = classroomResponse.classroom;
				} catch {}
			}
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		}
	};

	onMount(async () => {
		await loadData();
		loaded = true;
	});
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
				<div class="mb-8 rounded-3xl border border-gray-200 bg-white p-5">
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
										<div class="rounded-full bg-white px-2.5 py-1 text-xs text-gray-600">
											{item.project_mode === 'assignment_writing'
												? $i18n.t('Assignment Writing')
												: $i18n.t('Personal Writing')}
										</div>
									</div>
									<div class="mt-2 text-xs text-gray-500">
										{$i18n.t('Updated')}: {formatTimestamp(item.updated_at)}
									</div>
								</button>
							{/each}
						</div>
					{/if}
				</div>

				{#if ($user?.education_role || home?.role) === 'student'}
					<div class="mb-5 flex gap-2">
						<button
							class={`rounded-full px-4 py-2 text-sm ${activeTab === 'assignment' ? 'bg-black text-white' : 'border border-gray-300 bg-white text-gray-700'}`}
							on:click={() => (activeTab = 'assignment')}
						>
							{$i18n.t('Assignment Writing')}
						</button>
						<button
							class={`rounded-full px-4 py-2 text-sm ${activeTab === 'personal' ? 'bg-black text-white' : 'border border-gray-300 bg-white text-gray-700'}`}
							on:click={() => (activeTab = 'personal')}
						>
							{$i18n.t('Personal Writing')}
						</button>
					</div>

					{#if activeTab === 'assignment'}
						<div class="mb-8">
							<div class="mb-6 rounded-3xl border border-gray-200 bg-white p-5">
								<div class="mb-3 text-sm font-semibold">{$i18n.t('My Classroom')}</div>
								{#if home?.classroom}
									<div class="text-sm text-gray-600">
										{$i18n.t('You are connected to {{name}}.', {
											name: getClassroomNameForDisplay(home.classroom.name)
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
											class="flex-1 rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none"
											placeholder={$i18n.t('Enter classroom invite code')}
										/>
										<button
											class="rounded-full bg-black px-4 py-2 text-sm text-white disabled:opacity-60"
											on:click={joinCurrentClassroom}
											disabled={joining}
										>
											{joining ? $i18n.t('Joining...') : $i18n.t('Join Classroom')}
										</button>
									</div>
								{/if}
							</div>

							<div class="mb-4">
								<div class="text-lg font-semibold">{$i18n.t('Pending Assignments')}</div>
							</div>

							{#if (home?.assignment_items ?? []).length === 0}
								<div class="rounded-3xl border border-gray-200 bg-white p-6 text-sm text-gray-500">
									{$i18n.t('No assignments available yet.')}
								</div>
							{:else}
								<div class="grid gap-4">
									{#each home.assignment_items as item}
										<div class="rounded-3xl border border-gray-200 bg-white p-5">
											<div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
												<div>
													<div class="flex flex-wrap items-center gap-2">
														<div class="text-lg font-semibold">{item.assignment.title}</div>
														{#if item.review_status === 'returned'}
															<span
																class="rounded-full bg-rose-100 px-2 py-0.5 text-xs text-rose-700"
															>
																{$i18n.t('Returned')}
															</span>
														{:else if item.review_status === 'reviewed'}
															<span
																class="rounded-full bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700"
															>
																{$i18n.t('Reviewed')} {item.score ?? ''}
															</span>
														{:else if item.review_status === 'pending'}
															<span
																class="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600"
															>
																{$i18n.t('Awaiting review')}
															</span>
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
														{/if}
													</div>
												</div>

												<button
													class="rounded-full bg-black px-4 py-2 text-sm text-white"
													on:click={() => goto(`/assignments/${item.assignment.id}/write`)}
												>
													{$i18n.t('Open Assignment')}
												</button>
											</div>
										</div>
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
							<button
								class="w-full rounded-full bg-black px-4 py-2 text-sm text-white disabled:opacity-60 md:w-auto"
								on:click={startPersonalWriting}
								disabled={creatingPersonal}
							>
								{creatingPersonal ? $i18n.t('Creating...') : $i18n.t('New Writing')}
							</button>
						</div>
						<div class="mb-4 text-sm text-gray-500">{$i18n.t('Your personal drafts live here.')}</div>

						{#if (home?.personal_items ?? []).length === 0}
							<div class="rounded-3xl border border-gray-200 bg-white p-6 text-sm text-gray-500">
								{$i18n.t('No personal writing yet.')}
							</div>
						{:else}
							<div class="grid gap-4">
								{#each home.personal_items as item}
									<div class="rounded-3xl border border-gray-200 bg-white p-5">
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
												<button
													class="rounded-full border border-gray-300 px-4 py-2 text-sm text-gray-700"
													on:click={() => removePersonalWriting(item.writing_session.id)}
													disabled={deletingPersonalIds.has(item.writing_session.id)}
												>
													{deletingPersonalIds.has(item.writing_session.id)
														? $i18n.t('Deleting...')
														: $i18n.t('Delete')}
												</button>
												<button
													class="rounded-full bg-black px-4 py-2 text-sm text-white"
													on:click={() => goto(`/writing/${item.writing_session.id}`)}
												>
													{$i18n.t('Continue Writing')}
												</button>
											</div>
										</div>
									</div>
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
		<div class="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
			{loadError}
		</div>
	</div>
{/if}
