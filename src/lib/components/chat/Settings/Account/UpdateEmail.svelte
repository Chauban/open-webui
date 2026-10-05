<script lang="ts">
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { user } from '$lib/stores';
	import { updateUserEmail } from '$lib/apis/auths';
	import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';

	const i18n = getContext('i18n');

	let show = false;
	let newEmail = '';
	let currentPassword = '';
	const actionButtonClass =
		'text-xs text-gray-500 transition-colors hover:text-gray-900 dark:text-gray-500 dark:hover:text-white';

	const updateEmailHandler = async () => {
		const res = await updateUserEmail(localStorage.token, currentPassword, newEmail).catch(
			(error) => {
				toast.error(`${error}`);
				return null;
			}
		);

		if (res) {
			user.update((u) => (u ? { ...u, email: res.email } : u));
			toast.success($i18n.t('Email updated. Use the new email next time you sign in.'));
			newEmail = '';
			show = false;
		}

		currentPassword = '';
	};
</script>

<form
	class="flex flex-col text-sm"
	on:submit|preventDefault={() => {
		updateEmailHandler();
	}}
>
	<div class="flex items-center justify-between gap-2.5">
		<div class="text-xs text-gray-600 dark:text-gray-400">{$i18n.t('Change Email')}</div>
		<button
			class={actionButtonClass}
			type="button"
			on:click={() => {
				show = !show;
			}}>{show ? $i18n.t('Hide') : $i18n.t('Show')}</button
		>
	</div>
	<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
		{$i18n.t('Current sign-in email: {{email}}', { email: $user?.email ?? '' })}
	</p>

	{#if show}
		<div class="py-2.5 space-y-2.5">
			<div class="flex flex-col w-full">
				<div class="mb-1 text-xs text-gray-600 dark:text-gray-400">
					{$i18n.t('New Email')}
				</div>

				<input
					class="h-7 w-full rounded-lg border border-gray-100/50 bg-gray-50/40 px-2 text-xs text-gray-700 outline-hidden transition-colors placeholder:text-gray-300 focus:border-blue-400 dark:border-white/[0.04] dark:bg-white/[0.03] dark:text-gray-300 dark:placeholder:text-gray-700 dark:focus:border-blue-500"
					type="email"
					bind:value={newEmail}
					placeholder={$i18n.t('Enter your new email')}
					autocomplete="email"
					required
				/>
			</div>

			<div class="flex flex-col w-full">
				<div class="mb-1 text-xs text-gray-600 dark:text-gray-400">
					{$i18n.t('Current Password')}
				</div>

				<div class="flex-1">
					<SensitiveInput
						variant="settings"
						type="password"
						bind:value={currentPassword}
						placeholder={$i18n.t('Enter your current password')}
						autocomplete="current-password"
						required
					/>
				</div>
			</div>
		</div>

		<div class="flex justify-end">
			<button class={actionButtonClass}>
				{$i18n.t('Update email')}
			</button>
		</div>
	{/if}
</form>
