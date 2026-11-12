<script lang="ts">
	import { getContext } from 'svelte';
	import { EDU_FIELD_CLASS } from './styles';

	export let value = '';
	export let id: string;
	export let disabled = false;
	const i18n: any = getContext('i18n');
</script>

<div class="space-y-2">
	<label for={id} class="block text-sm font-medium">{$i18n.t('修改说明（必填）')}</label>
	<textarea
		{id}
		bind:value
		{disabled}
		required
		maxlength="1000"
		rows="3"
		class="w-full {EDU_FIELD_CLASS}"
		aria-describedby={`${id}-hint`}
		placeholder={$i18n.t('请说明本次修改了哪些内容及原因。')}
	></textarea>
	<p id={`${id}-hint`} class="text-xs text-gray-500">
		{$i18n.t('每次修改都需填写说明，填写后才能确认生效。')}
	</p>
</div>
