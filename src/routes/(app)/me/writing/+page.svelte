<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SidebarIcon from '$lib/components/icons/Sidebar.svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import { mobile, showSidebar, user } from '$lib/stores';

	const i18n = getContext('i18n');

	import {
		getMyClassroom,
		getStudentAssignments,
		getStudentDashboard,
		joinClassroom
	} from '$lib/apis/education';

	let assignments = [];
	let dashboard = null;
	let loadError = '';
	let loaded = false;
	let classroom = null;
	let inviteCode = '';
	let joining = false;
	let assignmentsError = '';
	let dashboardError = '';

	const loadData = async () => {
		loadError = '';
		assignmentsError = '';
		dashboardError = '';
		try {
			let classroomResponse = null;
			try {
				classroomResponse = await getMyClassroom(localStorage.token);
				classroom = classroomResponse.classroom;
			} catch (error) {
				classroom = null;
			}

			if (!classroom) {
				assignments = [];
				dashboard = { items: [] };
				return;
			}

			try {
				assignments = await getStudentAssignments(localStorage.token);
			} catch (error) {
				assignments = [];
				assignmentsError = `${error?.detail ?? error}`;
				toast.error(assignmentsError);
			}

			try {
				dashboard = await getStudentDashboard(localStorage.token);
			} catch (error) {
				dashboard = { items: [] };
				dashboardError = `${error?.detail ?? error}`;
				toast.error(dashboardError);
			}
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		}
	};

	const joinCurrentClassroom = async () => {
		if (!inviteCode.trim()) {
			toast.error('Invite code is required.');
			return;
		}

		joining = true;
		try {
			await joinClassroom(localStorage.token, { invite_code: inviteCode.trim() });
			inviteCode = '';
			await loadData();
			toast.success('Joined classroom.');
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			joining = false;
		}
	};

	onMount(async () => {
		const sessionUser = get(user);
		if (
			sessionUser?.education_role &&
			sessionUser.education_role !== 'student' &&
			sessionUser?.role !== 'admin'
		) {
			loadError = 'My Writing is only available for student accounts.';
			loaded = true;
			return;
		}
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
						<div class="text-xs uppercase tracking-[0.2em] text-gray-500">Student Dashboard</div>
						<h1 class="text-2xl font-semibold">My Writing</h1>
					</div>
				</div>
			</div>
		</nav>

		<div class="flex-1 overflow-y-auto">
			<div class="mx-auto max-w-6xl px-4 py-8">
				<div class="mb-8 rounded-3xl border border-gray-200 bg-white p-5">
					<div class="mb-3 text-sm font-semibold">My Classroom</div>
					{#if classroom}
						<div class="text-sm text-gray-600">
							You are connected to <span class="font-medium">{classroom.name}</span>.
						</div>
					{:else}
						<div class="text-sm text-gray-500">
							You have not joined a classroom yet. Enter your teacher's invite code to unlock assignments.
						</div>
						<div class="mt-4 flex flex-col gap-3 md:flex-row">
							<input
								bind:value={inviteCode}
								class="flex-1 rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none"
								placeholder="Enter classroom invite code"
							/>
							<button
								class="rounded-full bg-black px-4 py-2 text-sm text-white disabled:opacity-60"
								on:click={joinCurrentClassroom}
								disabled={joining}
							>
								{joining ? 'Joining...' : 'Join Classroom'}
							</button>
						</div>
					{/if}
				</div>

				<div class="mb-8">
					<div class="mb-4 flex items-center justify-between">
						<div>
							<div class="text-lg font-semibold">Assigned Tasks</div>
							<div class="text-sm text-gray-500">
								You can still open the original write link directly if your teacher sends it.
							</div>
						</div>
					</div>

					{#if assignments.length === 0}
						<div class="rounded-3xl border border-gray-200 bg-white p-6 text-sm text-gray-500">
							{classroom ? 'No assignments available yet.' : 'Join a classroom to see assignments.'}
						</div>
						{#if assignmentsError}
							<div class="mt-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
								{assignmentsError}
							</div>
						{/if}
					{:else}
						<div class="grid gap-4">
							{#each assignments as item}
								<div class="rounded-3xl border border-gray-200 bg-white p-5">
									<div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
										<div>
											<div class="text-lg font-semibold">{item.assignment.title}</div>
											<div class="mt-1 text-sm text-gray-500">
												{item.assignment.description || 'No description'}
											</div>
											<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
												<div>Status: {item.has_submission ? 'Submitted' : 'In progress'}</div>
												<div>Assignment ID: {item.assignment.id}</div>
											</div>
										</div>

										<div class="flex flex-wrap gap-2">
											<button
												class="rounded-full bg-black px-4 py-2 text-sm text-white"
												on:click={() => goto(`/assignments/${item.assignment.id}/write`)}
											>
												Open Task
											</button>
										</div>
									</div>
								</div>
							{/each}
						</div>
					{/if}
				</div>

				<div>
					<div class="mb-4">
						<div class="text-lg font-semibold">Submission History</div>
						<div class="text-sm text-gray-500">Review your previous writing statistics.</div>
					</div>

					{#if (dashboard?.items ?? []).length === 0}
						<div class="rounded-3xl border border-gray-200 bg-white p-6 text-sm text-gray-500">
							No submissions yet.
						</div>
						{#if dashboardError}
							<div class="mt-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
								{dashboardError}
							</div>
						{/if}
					{:else}
						<div class="grid gap-4">
							{#each dashboard.items as item}
								<div class="rounded-3xl border border-gray-200 bg-white p-5">
									<div class="text-sm text-gray-500">
										Submitted at: {new Date(item.submitted_at * 1000).toLocaleString()}
									</div>
									<div class="mt-3 grid gap-1 text-sm">
										<div>Typed: {item.source_stats.user_typed_chars ?? 0}</div>
										<div>AI inserted: {item.source_stats.ai_inserted_chars ?? 0}</div>
										<div>AI pasted: {item.source_stats.ai_pasted_chars ?? 0}</div>
										<div>Prompts: {item.prompt_count}</div>
									</div>
								</div>
							{/each}
						</div>
					{/if}
				</div>
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
