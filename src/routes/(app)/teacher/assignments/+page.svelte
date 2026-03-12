<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SidebarIcon from '$lib/components/icons/Sidebar.svelte';
	import { mobile, showSidebar } from '$lib/stores';

	const i18n = getContext('i18n');

	import {
		addAssignmentMember,
		createAssignment,
		getAssignmentMembers,
		getMyClassroom,
		getTeacherAssignments,
		regenerateClassroomInviteCode,
		removeAssignmentMember
	} from '$lib/apis/education';
	import { searchUsers } from '$lib/apis/users';

	let assignments = [];
	let membersByAssignment = {};
	let searchResultsByAssignment = {};
	let memberQueryByAssignment = {};
	let expandedAssignmentId = '';
	let loading = true;
	let loadError = '';

	let title = '';
	let description = '';
	let creating = false;
	let classroom = null;
	let classroomError = '';

	const loadAssignments = async () => {
		loading = true;
		loadError = '';
		try {
			assignments = await getTeacherAssignments(localStorage.token);
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		} finally {
			loading = false;
		}
	};

	const loadClassroom = async () => {
		classroomError = '';
		try {
			const response = await getMyClassroom(localStorage.token);
			classroom = response.classroom;
		} catch (error) {
			classroomError = `${error?.detail ?? error}`;
		}
	};

	const toggleAssignment = async (assignmentId: string) => {
		expandedAssignmentId = expandedAssignmentId === assignmentId ? '' : assignmentId;
		if (!expandedAssignmentId) return;

		await loadMembers(assignmentId);
	};

	const loadMembers = async (assignmentId: string) => {
		try {
			membersByAssignment = {
				...membersByAssignment,
				[assignmentId]: await getAssignmentMembers(localStorage.token, assignmentId)
			};
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		}
	};

	const submitCreateAssignment = async () => {
		if (!title.trim()) {
			toast.error('Assignment title is required.');
			return;
		}

		creating = true;
		try {
			await createAssignment(localStorage.token, {
				title: title.trim(),
				description: description.trim() || undefined,
				classroom_id: classroom?.id
			});
			title = '';
			description = '';
			await loadAssignments();
			toast.success('Assignment created.');
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			creating = false;
		}
	};

	const searchStudents = async (assignmentId: string) => {
		const query = memberQueryByAssignment[assignmentId]?.trim() ?? '';
		if (!query) {
			searchResultsByAssignment = { ...searchResultsByAssignment, [assignmentId]: [] };
			return;
		}

		try {
			const result = await searchUsers(localStorage.token, query, 'name', 'asc', 1);
			const existingMemberIds = new Set(
				(membersByAssignment[assignmentId] ?? []).map((item) => item.member.user_id)
			);
			const students = (result?.users ?? []).filter(
				(item) =>
					item?.role !== 'pending' &&
					item?.role !== 'admin' &&
					item?.info?.education_role === 'student' &&
					!existingMemberIds.has(item.id)
			);
			searchResultsByAssignment = { ...searchResultsByAssignment, [assignmentId]: students };
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		}
	};

	const copyWriteLink = async (assignmentId: string) => {
		const link = `${window.location.origin}/assignments/${assignmentId}/write`;
		try {
			await navigator.clipboard.writeText(link);
			toast.success('Write link copied.');
		} catch (error) {
			toast.error('Failed to copy write link.');
		}
	};

	const addStudent = async (assignmentId: string, studentId: string) => {
		try {
			await addAssignmentMember(localStorage.token, assignmentId, {
				user_id: studentId,
				member_role: 'student'
			});
			memberQueryByAssignment = { ...memberQueryByAssignment, [assignmentId]: '' };
			searchResultsByAssignment = { ...searchResultsByAssignment, [assignmentId]: [] };
			await Promise.all([loadAssignments(), loadMembers(assignmentId)]);
			toast.success('Student added.');
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		}
	};

	const removeStudent = async (assignmentId: string, studentId: string) => {
		try {
			await removeAssignmentMember(localStorage.token, assignmentId, studentId);
			await Promise.all([loadAssignments(), loadMembers(assignmentId)]);
			toast.success('Student removed.');
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		}
	};

	onMount(async () => {
		await Promise.all([loadClassroom(), loadAssignments()]);
	});
</script>

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
					<div class="text-xs uppercase tracking-[0.2em] text-gray-500">Teaching</div>
					<h1 class="text-2xl font-semibold">Assignments</h1>
					<div class="mt-1 text-sm text-gray-500">
						Create assignments and manage which students can join them.
					</div>
				</div>
			</div>
		</div>
	</nav>

	<div class="flex-1 overflow-y-auto">
		<div class="mx-auto max-w-6xl px-4 py-8">
			<div class="mb-8 rounded-3xl border border-gray-200 bg-white p-5">
				<div class="mb-3 flex items-center justify-between gap-4">
					<div>
						<div class="text-sm font-semibold">Classroom</div>
						<div class="mt-1 text-sm text-gray-500">
							Students join your classroom with this invite code, then all new assignments become visible to them.
						</div>
					</div>
					<button
						class="rounded-full border border-gray-300 px-4 py-2 text-sm"
						on:click={async () => {
							if (!classroom?.id) return;
							try {
								const response = await regenerateClassroomInviteCode(localStorage.token, classroom.id);
								classroom = response.classroom;
								toast.success('Invite code regenerated.');
							} catch (error) {
								toast.error(`${error?.detail ?? error}`);
							}
						}}
						disabled={!classroom?.id}
					>
						Regenerate Code
					</button>
				</div>

				{#if classroom}
					<div class="grid gap-2 text-sm">
						<div>Classroom Name: <span class="font-medium">{classroom.name}</span></div>
						<div>Invite Code: <span class="font-mono font-semibold">{classroom.invite_code}</span></div>
					</div>
				{:else if classroomError}
					<div class="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
						{classroomError}
					</div>
				{/if}
			</div>

			<div class="mb-8 rounded-3xl border border-gray-200 bg-white p-5">
				<div class="mb-4 text-sm font-semibold">Create Assignment</div>
				<div class="grid gap-3">
					<input
						bind:value={title}
						class="rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none"
						placeholder="Assignment title"
					/>
					<textarea
						bind:value={description}
						class="min-h-24 rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none"
						placeholder="Assignment description"
					></textarea>
					<div class="flex justify-end">
						<button
							class="rounded-full bg-black px-4 py-2 text-sm text-white disabled:opacity-60"
							on:click={submitCreateAssignment}
							disabled={creating}
						>
							{creating ? 'Creating...' : 'Create'}
						</button>
					</div>
				</div>
			</div>

			{#if loadError}
				<div class="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">{loadError}</div>
			{:else if loading}
				<div class="rounded-3xl border border-gray-200 bg-white p-6 text-sm text-gray-500">Loading assignments...</div>
			{:else if assignments.length === 0}
				<div class="rounded-3xl border border-gray-200 bg-white p-6 text-sm text-gray-500">No assignments yet.</div>
			{:else}
				<div class="grid gap-4">
					{#each assignments as item}
						<div class="rounded-3xl border border-gray-200 bg-white p-5">
							<div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
								<div>
									<div class="text-lg font-semibold text-gray-900">{item.assignment.title}</div>
									<div class="mt-1 text-sm text-gray-500">{item.assignment.description || 'No description'}</div>
									<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
										<div>Students: {item.student_count}</div>
										<div>Submissions: {item.submission_count}</div>
										<div>Assignment ID: {item.assignment.id}</div>
									</div>
								</div>

								<div class="flex flex-wrap gap-2">
									<button
										class="rounded-full border border-gray-300 px-3 py-2 text-sm"
										on:click={() => goto(`/assignments/${item.assignment.id}/write`)}
									>
										Open Writer
									</button>
									<button
										class="rounded-full border border-gray-300 px-3 py-2 text-sm"
										on:click={() => copyWriteLink(item.assignment.id)}
									>
										Copy Link
									</button>
									<button
										class="rounded-full border border-gray-300 px-3 py-2 text-sm"
										on:click={() => goto(`/teacher/assignments/${item.assignment.id}/submissions`)}
									>
										Submissions
									</button>
									<button
										class="rounded-full border border-gray-300 px-3 py-2 text-sm"
										on:click={() => goto(`/teacher/assignments/${item.assignment.id}/dashboard`)}
									>
										Dashboard
									</button>
									<button
										class="rounded-full bg-gray-100 px-3 py-2 text-sm"
										on:click={() => toggleAssignment(item.assignment.id)}
									>
										{expandedAssignmentId === item.assignment.id ? 'Hide Students' : 'Manage Students'}
									</button>
								</div>
							</div>

							{#if expandedAssignmentId === item.assignment.id}
								<div class="mt-5 grid gap-5 border-t border-gray-100 pt-5 lg:grid-cols-[0.9fr_1.1fr]">
									<div>
										<div class="mb-2 text-sm font-semibold">Add Student</div>
										<div class="flex gap-2">
											<input
												class="flex-1 rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none"
												placeholder="Search by student name or email"
												value={memberQueryByAssignment[item.assignment.id] ?? ''}
												on:input={(event) => {
													memberQueryByAssignment = {
														...memberQueryByAssignment,
														[item.assignment.id]: event.currentTarget.value
													};
												}}
											/>
											<button
												class="rounded-full bg-black px-4 py-2 text-sm text-white"
												on:click={() => searchStudents(item.assignment.id)}
											>
												Search
											</button>
										</div>

										{#if (searchResultsByAssignment[item.assignment.id] ?? []).length > 0}
											<div class="mt-3 space-y-2">
												{#each searchResultsByAssignment[item.assignment.id] as candidate}
													<div class="flex items-center justify-between rounded-2xl border border-gray-200 px-3 py-3 text-sm">
														<div>
															<div class="font-medium">{candidate.name}</div>
															<div class="text-xs text-gray-500">{candidate.email}</div>
														</div>
														<button
															class="rounded-full border border-gray-300 px-3 py-1.5 text-sm"
															on:click={() => addStudent(item.assignment.id, candidate.id)}
														>
															Add
														</button>
													</div>
												{/each}
											</div>
										{/if}
									</div>

									<div>
										<div class="mb-2 text-sm font-semibold">Current Students</div>
										{#if (membersByAssignment[item.assignment.id] ?? []).length === 0}
											<div class="rounded-2xl border border-dashed border-gray-300 px-4 py-5 text-sm text-gray-500">
												No students assigned yet.
											</div>
										{:else}
											<div class="space-y-2">
												{#each membersByAssignment[item.assignment.id] as member}
													<div class="flex items-center justify-between rounded-2xl border border-gray-200 px-4 py-3 text-sm">
														<div>
															<div class="font-medium">{member.user_name}</div>
															<div class="text-xs text-gray-500">{member.user_email}</div>
														</div>
														<button
															class="rounded-full border border-red-300 px-3 py-1.5 text-sm text-red-600"
															on:click={() => removeStudent(item.assignment.id, member.member.user_id)}
														>
															Remove
														</button>
													</div>
												{/each}
											</div>
										{/if}
									</div>
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</div>
</div>
