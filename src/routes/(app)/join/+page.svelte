<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { getMyClassroom, joinClassroom } from '$lib/apis/education';
	import { getClassroomDisplayName, resolveErrorMessage } from '$lib/utils/education';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduDataNotice from '$lib/components/education/EduDataNotice.svelte';
	import EduTile from '$lib/components/education/EduTile.svelte';
	import { EDU_FIELD_CLASS } from '$lib/components/education/styles';
	import { user } from '$lib/stores';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let inviteCode = '';
	let joining = false;
	// 一个学生只能在一个班：已入班时只提示当前班级，不再给加入入口。
	let currentClassroomName: string | null = null;
	let checkingClassroom = true;

	$: educationRole = $user?.education_role ?? null;
	$: isStudent = educationRole === 'student';

	onMount(async () => {
		inviteCode = get(page).url.searchParams.get('code') ?? '';
		if (get(user)?.education_role === 'student') {
			// 404 表示还没加入任何班级，正常展示加入表单。
			const response = await getMyClassroom(localStorage.token).catch(() => null);
			currentClassroomName = response?.classroom?.name ?? null;
		}
		checkingClassroom = false;
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
			toast.error(resolveErrorMessage(error, t));
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
		{:else if checkingClassroom}
			<div class="mt-6 text-sm text-gray-500 dark:text-gray-400">{$i18n.t('Loading...')}</div>
		{:else if currentClassroomName !== null}
			<EduTile tone="amber" class="mt-6 text-amber-700 dark:text-amber-300">
				{$i18n.t(
					'You are already in {{name}}. Each student can be in only one classroom. To change classes, ask your teacher or an administrator.',
					{ name: getClassroomDisplayName(currentClassroomName, t) }
				)}
			</EduTile>
			<EduButton class="mt-6 w-full" on:click={() => goto('/me/writing')}>
				{$i18n.t('Back to Writing Home')}
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
			<!-- 加入班级是学生第一次被纳入教师可见范围，告知放在动作之前。 -->
			<EduDataNotice scope="classroom" class="mt-6" />
			<EduButton variant="primary" class="mt-6 w-full" disabled={joining} on:click={join}>
				{joining ? $i18n.t('Joining...') : $i18n.t('Join Classroom')}
			</EduButton>
			<EduButton class="mt-3 w-full" on:click={() => goto('/me/writing')}>
				{$i18n.t('Back to Writing Home')}
			</EduButton>
		{/if}
	</EduCard>
</div>
