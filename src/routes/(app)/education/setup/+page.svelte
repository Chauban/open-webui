<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { user } from '$lib/stores';
	import { createClassroom, getMyClassroom, getTeacherClassrooms, joinClassroom } from '$lib/apis/education';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let classroomName = '';
	let inviteCode = '';
	let submitting = false;
	let checking = true;

	$: educationRole = $user?.info?.education_role ?? null;

	onMount(async () => {
		// 引导页守卫:身份在注册时选定、由管理员管理,这里只做首次初始化;已完成初始化的直接跳走
		const current = get(user);
		const role = current?.info?.education_role ?? null;

		if (current?.role === 'admin') {
			goto('/teacher');
			return;
		}

		if (role === 'teacher') {
			try {
				const classrooms = await getTeacherClassrooms(localStorage.token);
				if ((classrooms ?? []).length > 0) {
					goto('/teacher');
					return;
				}
			} catch {}
		} else if (role === 'student') {
			try {
				await getMyClassroom(localStorage.token);
				goto('/me/writing');
				return;
			} catch {}
		} else {
			goto('/');
			return;
		}

		checking = false;
	});

	const saveSetup = async () => {
		submitting = true;
		try {
			if (educationRole === 'teacher') {
				const trimmedName = classroomName.trim();
				if (!trimmedName) {
					toast.error(t('Classroom name is required.'));
					return;
				}

				await createClassroom(localStorage.token, {
					name: trimmedName
				});
				toast.success(t('Your first classroom is ready.'));
				await goto('/teacher');
				return;
			}

			if (inviteCode.trim()) {
				await joinClassroom(localStorage.token, {
					invite_code: inviteCode.trim()
				});
				toast.success(t('Classroom joined.'));
			}

			await goto('/me/writing');
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			submitting = false;
		}
	};
</script>

{#if !checking}
	<div class="mx-auto max-w-3xl px-4 py-10">
		<div class="mb-8">
			<div class="text-xs uppercase tracking-[0.2em] text-gray-500">{$i18n.t('Education')}</div>
			<h1 class="text-3xl font-semibold text-gray-900">
				{educationRole === 'teacher'
					? $i18n.t('Welcome, teacher')
					: $i18n.t('Welcome, student')}
			</h1>
			<div class="mt-2 text-sm text-gray-500">
				{educationRole === 'teacher'
					? $i18n.t('Create your first classroom to start assigning writing tasks.')
					: $i18n.t('Join your classroom with an invite code, or skip and join later.')}
			</div>
		</div>

		<div class="rounded-[28px] border border-gray-200 bg-white p-6 shadow-sm">
			{#if educationRole === 'teacher'}
				<div>
					<div class="mb-2 text-sm font-semibold text-gray-900">{$i18n.t('Classroom Name')}</div>
					<input
						bind:value={classroomName}
						class="w-full rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none"
						placeholder={$i18n.t('Example: Grade 8 Writing')}
					/>
					<div class="mt-2 text-sm text-gray-500">
						{$i18n.t('Create your first classroom now. You can add more classrooms later from Teaching.')}
					</div>
				</div>
			{:else}
				<div>
					<div class="mb-2 text-sm font-semibold text-gray-900">
						{$i18n.t('Classroom Invite Code')}
					</div>
					<input
						bind:value={inviteCode}
						class="w-full rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none"
						placeholder={$i18n.t('Enter invite code now, or leave blank and join later')}
					/>
					<div class="mt-2 text-sm text-gray-500">
						{$i18n.t('You can skip this now. The invite code can also be entered later in Writing.')}
					</div>
				</div>
			{/if}

			<div class="mt-8 flex justify-end">
				<button
					class="rounded-full bg-black px-5 py-2.5 text-sm font-medium text-white disabled:opacity-60"
					on:click={saveSetup}
					disabled={submitting}
				>
					{submitting ? $i18n.t('Saving...') : $i18n.t('Save and Continue')}
				</button>
			</div>
		</div>
	</div>
{/if}
