<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { joinClassroom } from '$lib/apis/education';
	import { user } from '$lib/stores';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let inviteCode = '';
	let joining = false;

	$: educationRole = $user?.info?.education_role ?? null;
	$: isStudent = educationRole === 'student';

	onMount(() => {
		inviteCode = get(page).url.searchParams.get('code') ?? '';
	});

	const join = async () => {
		if (!inviteCode.trim()) {
			toast.error(t('Classroom invite code is required.'));
			return;
		}
		joining = true;
		try {
			const response = await joinClassroom(localStorage.token, {
				invite_code: inviteCode.trim()
			});
			toast.success(
				t('Joined classroom {{name}}.', { name: response.classroom?.name ?? '' })
			);
			goto('/me/writing');
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			joining = false;
		}
	};
</script>

<div class="flex min-h-full w-full items-center justify-center px-4 py-16">
	<div class="w-full max-w-md rounded-3xl border border-gray-200 bg-white p-8 dark:border-gray-800 dark:bg-gray-900">
		<div class="text-xs uppercase tracking-[0.2em] text-gray-400">{$i18n.t('Classroom Invite')}</div>
		<h1 class="mt-1 text-2xl font-semibold">{$i18n.t('Join Classroom')}</h1>

		{#if !isStudent}
			<div class="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
				{$i18n.t('Only students can join classrooms with an invite code.')}
			</div>
			<button
				class="mt-6 w-full rounded-full border border-gray-300 px-4 py-2.5 text-sm"
				on:click={() => goto(educationRole === 'teacher' ? '/teacher' : '/')}
			>
				{$i18n.t('Back')}
			</button>
		{:else}
			<div class="mt-6">
				<label class="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Invite Code')}
				</label>
				<input
					bind:value={inviteCode}
					class="w-full rounded-2xl border border-gray-300 px-4 py-3 font-mono text-sm outline-none focus:border-gray-500 dark:border-gray-700 dark:bg-gray-800"
					placeholder={$i18n.t('Enter invite code')}
				/>
			</div>
			<button
				class="mt-6 w-full rounded-full bg-black px-4 py-2.5 text-sm text-white disabled:opacity-60 dark:bg-white dark:text-black"
				disabled={joining}
				on:click={join}
			>
				{joining ? $i18n.t('Joining...') : $i18n.t('Join Classroom')}
			</button>
			<button
				class="mt-3 w-full rounded-full border border-gray-300 px-4 py-2.5 text-sm dark:border-gray-700"
				on:click={() => goto('/me/writing')}
			>
				{$i18n.t('Back to Writing Home')}
			</button>
		{/if}
	</div>
</div>
