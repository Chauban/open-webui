<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	const dispatch = createEventDispatcher();

	import RecursiveFolder from './RecursiveFolder.svelte';
	import { chatId, selectedFolder } from '$lib/stores';

	export let folderRegistry = {};

	export let folders = {};
	export let shiftKey = false;
	export let lockFolders = false;
	export let folderHrefBuilder: ((folder: any) => string) | null = null;
	export let chatHrefBuilder: ((chat: any, folder: any) => string) | null = null;
	export let clearSelectedProjectOnChatClick = true;
	export let allowMenuWhenLocked = false;
	export let closeFolderLabel = 'Close';
	export let closeFolderLabelBuilder: ((folder: any) => string) | null = null;
	export let onCloseFolder = async (folder) => {};
	export let showVisibilityToggle = false;

	export let onDelete = (folderId) => {};

	let folderList = [];
	// Get the list of folders that have no parent, sorted by name alphabetically
	$: folderList = Object.keys(folders)
		.filter((key) => folders[key].parent_id === null)
		.sort((a, b) =>
			folders[a].name.localeCompare(folders[b].name, undefined, {
				numeric: true,
				sensitivity: 'base'
			})
		);

	const onItemMove = (e) => {
		if (e.originFolderId) {
			folderRegistry[e.originFolderId]?.setFolderItems();
		}
	};

	const loadFolderItems = () => {
		for (const folderId of Object.keys(folders)) {
			folderRegistry[folderId]?.setFolderItems();
		}
	};

	$: if (folders || ($selectedFolder && $chatId)) {
		loadFolderItems();
	}
</script>

{#each folderList as folderId (folderId)}
	<RecursiveFolder
		className=""
		bind:folderRegistry
		{folders}
		{folderId}
		{shiftKey}
		{lockFolders}
		{folderHrefBuilder}
		{chatHrefBuilder}
		{clearSelectedProjectOnChatClick}
		{allowMenuWhenLocked}
		{closeFolderLabel}
		{closeFolderLabelBuilder}
		{onCloseFolder}
		{showVisibilityToggle}
		{onDelete}
		{onItemMove}
		on:import={(e) => {
			dispatch('import', e.detail);
		}}
		on:update={(e) => {
			dispatch('update', e.detail);
		}}
		on:change={(e) => {
			dispatch('change', e.detail);
		}}
	/>
{/each}
