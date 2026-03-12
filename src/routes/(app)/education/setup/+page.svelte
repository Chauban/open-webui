<script lang="ts">
	// @ts-nocheck
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';

	import { user } from '$lib/stores';
	import { updateUserInfo } from '$lib/apis/users';
	import { createClassroom, joinClassroom } from '$lib/apis/education';

	let educationRole = 'teacher';
	let classroomName = '';
	let inviteCode = '';
	let submitting = false;

	const syncEducationRole = (role: string) => {
		user.update((current) => {
			if (!current) return current;
			return {
				...current,
				education_role: role
			};
		});
	};

	const saveSetup = async () => {
		submitting = true;
		try {
			await updateUserInfo(localStorage.token, {
				education_role: educationRole
			});
			syncEducationRole(educationRole);

			if (educationRole === 'teacher') {
				await createClassroom(localStorage.token, {
					name: classroomName.trim() || 'Default Classroom'
				});
				toast.success('Teacher identity saved. Your classroom is ready.');
				await goto('/teacher/assignments');
				return;
			}

			if (inviteCode.trim()) {
				await joinClassroom(localStorage.token, {
					invite_code: inviteCode.trim()
				});
				toast.success('Student identity saved and classroom joined.');
			} else {
				toast.success('Student identity saved. You can join a classroom later.');
			}

			await goto('/me/writing');
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			submitting = false;
		}
	};
</script>

<div class="mx-auto max-w-3xl px-4 py-10">
	<div class="mb-8">
		<div class="text-xs uppercase tracking-[0.2em] text-gray-500">Education</div>
		<h1 class="text-3xl font-semibold text-gray-900">Set up your teaching identity</h1>
		<div class="mt-2 text-sm text-gray-500">
			Choose how this account should participate in the writing platform.
		</div>
	</div>

	<div class="rounded-[28px] border border-gray-200 bg-white p-6 shadow-sm">
		<div class="mb-5 text-sm font-semibold text-gray-900">Role</div>
		<div class="grid gap-3 md:grid-cols-2">
			<button
				class={`rounded-3xl border px-5 py-4 text-left transition ${
					educationRole === 'teacher'
						? 'border-black bg-black text-white'
						: 'border-gray-200 bg-white text-gray-900'
				}`}
				on:click={() => (educationRole = 'teacher')}
			>
				<div class="text-base font-semibold">Teacher</div>
				<div class={`mt-1 text-sm ${educationRole === 'teacher' ? 'text-gray-200' : 'text-gray-500'}`}>
					Create a classroom, share an invite code, and publish assignments.
				</div>
			</button>

			<button
				class={`rounded-3xl border px-5 py-4 text-left transition ${
					educationRole === 'student'
						? 'border-black bg-black text-white'
						: 'border-gray-200 bg-white text-gray-900'
				}`}
				on:click={() => (educationRole = 'student')}
			>
				<div class="text-base font-semibold">Student</div>
				<div class={`mt-1 text-sm ${educationRole === 'student' ? 'text-gray-200' : 'text-gray-500'}`}>
					Join a teacher's classroom and see assigned writing tasks.
				</div>
			</button>
		</div>

		{#if educationRole === 'teacher'}
			<div class="mt-6">
				<div class="mb-2 text-sm font-semibold text-gray-900">Classroom Name</div>
				<input
					bind:value={classroomName}
					class="w-full rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none"
					placeholder="Example: Grade 8 Writing"
				/>
				<div class="mt-2 text-sm text-gray-500">
					If left empty, the system will create a default classroom for this teacher account.
				</div>
			</div>
		{:else}
			<div class="mt-6">
				<div class="mb-2 text-sm font-semibold text-gray-900">Classroom Invite Code</div>
				<input
					bind:value={inviteCode}
					class="w-full rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none"
					placeholder="Enter invite code now, or leave blank and join later"
				/>
				<div class="mt-2 text-sm text-gray-500">
					You can skip this now. The invite code can also be entered later in My Writing.
				</div>
			</div>
		{/if}

		<div class="mt-8 flex justify-end">
			<button
				class="rounded-full bg-black px-5 py-2.5 text-sm font-medium text-white disabled:opacity-60"
				on:click={saveSetup}
				disabled={submitting}
			>
				{submitting ? 'Saving...' : 'Save and Continue'}
			</button>
		</div>
	</div>
</div>
