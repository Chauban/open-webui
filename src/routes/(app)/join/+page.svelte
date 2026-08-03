<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { joinClassroom } from '$lib/apis/education';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduTile from '$lib/components/education/EduTile.svelte';
	import { EDU_FIELD_CLASS } from '$lib/components/education/styles';
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
	<EduCard padding="lg" class="w-full max-w-md">
		<div class="text-xs uppercase tracking-[0.2em] text-gray-400">{$i18n.t('Classroom Invite')}</div>
		<h1 class="mt-1 text-2xl font-semibold">{$i18n.t('Join Classroom')}</h1>

		{#if !isStudent}
			<EduTile tone="amber" class="mt-6 text-amber-700 dark:text-amber-300">
				{$i18n.t('Only students can join classrooms with an invite code.')}
			</EduTile>
			<EduButton
				class="mt-6 w-full"
				on:click={() => goto(educationRole === 'teacher' ? '/teacher' : '/')}
			>
				{$i18n.t('Back')}
			</EduButton>
		{:else}
			<div class="mt-6">
				<label class="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Invite Code')}
				</label>
				<input
					bind:value={inviteCode}
					class="w-full font-mono {EDU_FIELD_CLASS}"
					placeholder={$i18n.t('Enter invite code')}
				/>
			</div>
			<EduButton variant="primary" class="mt-6 w-full" disabled={joining} on:click={join}>
				{joining ? $i18n.t('Joining...') : $i18n.t('Join Classroom')}
			</EduButton>
			<EduButton class="mt-3 w-full" on:click={() => goto('/me/writing')}>
				{$i18n.t('Back to Writing Home')}
			</EduButton>
		{/if}
	</EduCard>
</div>
