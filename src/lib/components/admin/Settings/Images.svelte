<script lang="ts">
	import { toast } from 'svelte-sonner';

	import { createEventDispatcher, onMount, getContext } from 'svelte';
	import { config as backendConfig, user } from '$lib/stores';

	import { getBackendConfig } from '$lib/apis';
	import {
		getImageGenerationModels,
		getImageGenerationConfig,
		updateImageGenerationConfig,
		getConfig,
		updateConfig
	} from '$lib/apis/images';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Textarea from '$lib/components/common/Textarea.svelte';
	const dispatch = createEventDispatcher();

	const i18n = getContext('i18n');

	let loading = false;

	let models = null;
	let config = null;

	const getModels = async () => {
		models = await getImageGenerationModels(localStorage.token).catch((error) => {
			toast.error(`${error}`);
			return null;
		});
	};

	const updateConfigHandler = async () => {
		if (config.IMAGE_GENERATION_ENGINE === 'openai' && config.IMAGES_OPENAI_API_KEY === '') {
			toast.error($i18n.t('OpenAI API Key is required.'));
			config.ENABLE_IMAGE_GENERATION = false;

			return null;
		} else if (config.IMAGE_GENERATION_ENGINE === 'gemini' && config.IMAGES_GEMINI_API_KEY === '') {
			toast.error($i18n.t('Gemini API Key is required.'));
			config.ENABLE_IMAGE_GENERATION = false;

			return null;
		}

		const res = await updateConfig(localStorage.token, {
			...config,
			IMAGES_OPENAI_API_PARAMS:
				typeof config.IMAGES_OPENAI_API_PARAMS === 'string' &&
				config.IMAGES_OPENAI_API_PARAMS.trim() !== ''
					? JSON.parse(config.IMAGES_OPENAI_API_PARAMS)
					: {}
		}).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			if (res.ENABLE_IMAGE_GENERATION) {
				backendConfig.set(await getBackendConfig());
				getModels();
			}

			return res;
		}

		return null;
	};

	const saveHandler = async () => {
		loading = true;

		const res = await updateConfigHandler();
		if (res) {
			dispatch('save');
		}

		loading = false;
	};

	onMount(async () => {
		if ($user?.role === 'admin') {
			const res = await getConfig(localStorage.token).catch((error) => {
				toast.error(`${error}`);
				return null;
			});

			if (res) {
				config = res;
			}

			if (config.ENABLE_IMAGE_GENERATION) {
				getModels();
			}

			config.IMAGES_OPENAI_API_PARAMS =
				typeof config.IMAGES_OPENAI_API_PARAMS === 'object'
					? JSON.stringify(config.IMAGES_OPENAI_API_PARAMS ?? {}, null, 2)
					: config.IMAGES_OPENAI_API_PARAMS;
		}
	});
</script>

<form
	class="flex flex-col h-full justify-between space-y-3 text-sm"
	on:submit|preventDefault={async () => {
		saveHandler();
	}}
>
	<div class=" space-y-3 overflow-y-scroll scrollbar-hidden pr-2">
		{#if config}
			<div>
				<div class="mb-3">
					<div class=" mt-0.5 mb-2.5 text-base font-medium">{$i18n.t('General')}</div>

					<hr class=" border-gray-100/30 dark:border-gray-850/30 my-2" />

					<div class="mb-2.5">
						<div class="flex w-full justify-between items-center">
							<div class="text-xs pr-2">
								<div class="">
									{$i18n.t('Image Generation')}
								</div>
							</div>

							<Switch bind:state={config.ENABLE_IMAGE_GENERATION} />
						</div>
					</div>
				</div>

				<div class="mb-3">
					<div class=" mt-0.5 mb-2.5 text-base font-medium">{$i18n.t('Create Image')}</div>

					<hr class=" border-gray-100/30 dark:border-gray-850/30 my-2" />

					{#if config.ENABLE_IMAGE_GENERATION}
						<div class="mb-2.5">
							<div class="flex w-full justify-between items-center">
								<div class="text-xs pr-2">
									<div class="shrink-0">
										{$i18n.t('Model')}
									</div>
								</div>

								<Tooltip content={$i18n.t('Enter Model ID')} placement="top-start">
									<input
										list="model-list"
										class=" text-right text-sm bg-transparent outline-hidden max-w-full w-52"
										bind:value={config.IMAGE_GENERATION_MODEL}
										placeholder={$i18n.t('Select a model')}
										required
									/>

									<datalist id="model-list">
										{#each models ?? [] as model}
											<option value={model.id}>{model.name}</option>
										{/each}
									</datalist>
								</Tooltip>
							</div>
						</div>

						<div class="mb-2.5">
							<div class="flex w-full justify-between items-center">
								<div class="text-xs pr-2">
									<div class="shrink-0">
										{$i18n.t('Image Size')}
									</div>
								</div>

								<Tooltip content={$i18n.t('Enter Image Size (e.g. 512x512)')} placement="top-start">
									<input
										class="  text-right text-sm bg-transparent outline-hidden max-w-full w-52"
										placeholder={$i18n.t('Enter Image Size (e.g. 512x512)')}
										bind:value={config.IMAGE_SIZE}
									/>
								</Tooltip>
							</div>
						</div>

						<div class="mb-2.5">
							<div class="flex w-full justify-between items-center">
								<div class="text-xs pr-2">
									<div class="">
										{$i18n.t('Image Prompt Generation')}
									</div>
								</div>

								<Switch bind:state={config.ENABLE_IMAGE_PROMPT_GENERATION} />
							</div>
						</div>
					{/if}

					<div class="mb-2.5">
						<div class="flex w-full justify-between items-center">
							<div class="text-xs pr-2">
								<div class="">
									{$i18n.t('Image Generation Engine')}
								</div>
							</div>

							<select
								class="w-fit pr-8 cursor-pointer rounded-sm px-2 text-xs bg-transparent outline-hidden text-right"
								bind:value={config.IMAGE_GENERATION_ENGINE}
								placeholder={$i18n.t('Select Engine')}
							>
								<option value="openai">{$i18n.t('Default (Open AI)')}</option>
								<option value="gemini">{$i18n.t('Gemini')}</option>
							</select>
						</div>
					</div>

					{#if config?.IMAGE_GENERATION_ENGINE === 'openai'}
						<div class="mb-2.5">
							<div class="flex w-full justify-between items-center">
								<div class="text-xs pr-2 shrink-0">
									<div class="">
										{$i18n.t('OpenAI API Base URL')}
									</div>
								</div>

								<div class="flex w-full">
									<div class="flex-1">
										<input
											class="w-full text-sm bg-transparent outline-hidden text-right"
											placeholder={$i18n.t('API Base URL')}
											bind:value={config.IMAGES_OPENAI_API_BASE_URL}
										/>
									</div>
								</div>
							</div>
						</div>

						<div class="mb-2.5">
							<div class="flex w-full justify-between items-center">
								<div class="text-xs pr-2 shrink-0">
									<div class="">
										{$i18n.t('OpenAI API Key')}
									</div>
								</div>

								<div class="flex w-full">
									<div class="flex-1">
										<SensitiveInput
											inputClassName="text-right w-full"
											placeholder={$i18n.t('API Key')}
											bind:value={config.IMAGES_OPENAI_API_KEY}
											required={false}
										/>
									</div>
								</div>
							</div>
						</div>

						<div class="mb-2.5">
							<div class="flex w-full justify-between items-center">
								<div class="text-xs pr-2 shrink-0">
									<div class="">
										{$i18n.t('OpenAI API Version')}
									</div>
								</div>

								<div class="flex w-full">
									<div class="flex-1">
										<input
											class="w-full text-sm bg-transparent outline-hidden text-right"
											placeholder={$i18n.t('API Version')}
											bind:value={config.IMAGES_OPENAI_API_VERSION}
										/>
									</div>
								</div>
							</div>
						</div>

						<div class="mb-2.5">
							<div class="flex w-full justify-between items-center">
								<div class="text-xs pr-2 shrink-0">
									<div class="">
										{$i18n.t('Additional Parameters')}
									</div>
								</div>
							</div>
							<div class="mt-1.5 flex w-full">
								<div class="flex-1 mr-2">
									<Textarea
										className="rounded-lg w-full py-2 px-3 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
										bind:value={config.IMAGES_OPENAI_API_PARAMS}
										placeholder={$i18n.t('Enter additional parameters in JSON format')}
										minSize={100}
									/>
								</div>
							</div>
						</div>
					{:else if config?.IMAGE_GENERATION_ENGINE === 'gemini'}
						<div class="mb-2.5">
							<div class="flex w-full justify-between items-center">
								<div class="text-xs pr-2 shrink-0">
									<div class="">
										{$i18n.t('Gemini Base URL')}
									</div>
								</div>

								<div class="flex w-full">
									<div class="flex-1">
										<input
											class="w-full text-sm bg-transparent outline-hidden text-right"
											placeholder={$i18n.t('API Base URL')}
											bind:value={config.IMAGES_GEMINI_API_BASE_URL}
										/>
									</div>
								</div>
							</div>
						</div>

						<div class="mb-2.5">
							<div class="flex w-full justify-between items-center">
								<div class="text-xs pr-2 shrink-0">
									<div class="">
										{$i18n.t('Gemini API Key')}
									</div>
								</div>

								<div class="flex w-full">
									<div class="flex-1">
										<SensitiveInput
											inputClassName="text-right w-full"
											placeholder={$i18n.t('API Key')}
											bind:value={config.IMAGES_GEMINI_API_KEY}
											required={true}
										/>
									</div>
								</div>
							</div>
						</div>

						<div class="mb-2.5">
							<div class="flex w-full justify-between items-center">
								<div class="text-xs pr-2">
									<div class="">
										{$i18n.t('Gemini Endpoint Method')}
									</div>
								</div>

								<select
									class="w-fit pr-8 cursor-pointer rounded-sm px-2 text-xs bg-transparent outline-hidden text-right"
									bind:value={config.IMAGES_GEMINI_ENDPOINT_METHOD}
									placeholder={$i18n.t('Select Method')}
								>
									<option value="predict">predict</option>
									<option value="generateContent">generateContent</option>
								</select>
							</div>
						</div>
					{/if}
				</div>

				<div class="mb-3">
					<div class=" mt-0.5 mb-2.5 text-base font-medium">{$i18n.t('Edit Image')}</div>

					<hr class=" border-gray-100/30 dark:border-gray-850/30 my-2" />

					<div class="mb-2.5">
						<div class="flex w-full justify-between items-center">
							<div class="text-xs pr-2">
								<div class="">
									{$i18n.t('Image Edit')}
								</div>
							</div>

							<Switch bind:state={config.ENABLE_IMAGE_EDIT} />
						</div>
					</div>

					{#if config?.ENABLE_IMAGE_GENERATION && config?.ENABLE_IMAGE_EDIT}
						<div class="mb-2.5">
							<div class="flex w-full justify-between items-center">
								<div class="text-xs pr-2">
									<div class="shrink-0">
										{$i18n.t('Model')}
									</div>
								</div>

								<Tooltip content={$i18n.t('Enter Model ID')} placement="top-start">
									<input
										list="model-list"
										class="text-right text-sm bg-transparent outline-hidden max-w-full w-52"
										bind:value={config.IMAGE_EDIT_MODEL}
										placeholder={$i18n.t('Select a model')}
									/>

									<datalist id="model-list">
										{#each models ?? [] as model}
											<option value={model.id}>{model.name}</option>
										{/each}
									</datalist>
								</Tooltip>
							</div>
						</div>

						<div class="mb-2.5">
							<div class="flex w-full justify-between items-center">
								<div class="text-xs pr-2">
									<div class="shrink-0">
										{$i18n.t('Image Size')}
									</div>
								</div>

								<Tooltip content={$i18n.t('Enter Image Size (e.g. 512x512)')} placement="top-start">
									<input
										class="text-right text-sm bg-transparent outline-hidden max-w-full w-52"
										placeholder={$i18n.t('Enter Image Size (e.g. 512x512)')}
										bind:value={config.IMAGE_EDIT_SIZE}
									/>
								</Tooltip>
							</div>
						</div>
					{/if}

					<div class="mb-2.5">
						<div class="flex w-full justify-between items-center">
							<div class="text-xs pr-2">
								<div class="">
									{$i18n.t('Image Edit Engine')}
								</div>
							</div>

							<select
								class="w-fit pr-8 cursor-pointer rounded-sm px-2 text-xs bg-transparent outline-hidden text-right"
								bind:value={config.IMAGE_EDIT_ENGINE}
								placeholder={$i18n.t('Select Engine')}
							>
								<option value="openai">{$i18n.t('Default (Open AI)')}</option>
								<option value="gemini">{$i18n.t('Gemini')}</option>
							</select>
						</div>
					</div>

					{#if config?.IMAGE_EDIT_ENGINE === 'openai'}
						<div class="mb-2.5">
							<div class="flex w-full justify-between items-center">
								<div class="text-xs pr-2 shrink-0">
									<div class="">
										{$i18n.t('OpenAI API Base URL')}
									</div>
								</div>

								<div class="flex w-full">
									<div class="flex-1">
										<input
											class="w-full text-sm bg-transparent outline-hidden text-right"
											placeholder={$i18n.t('API Base URL')}
											bind:value={config.IMAGES_EDIT_OPENAI_API_BASE_URL}
										/>
									</div>
								</div>
							</div>
						</div>

						<div class="mb-2.5">
							<div class="flex w-full justify-between items-center">
								<div class="text-xs pr-2 shrink-0">
									<div class="">
										{$i18n.t('OpenAI API Key')}
									</div>
								</div>

								<div class="flex w-full">
									<div class="flex-1">
										<SensitiveInput
											inputClassName="text-right w-full"
											placeholder={$i18n.t('API Key')}
											bind:value={config.IMAGES_EDIT_OPENAI_API_KEY}
											required={false}
										/>
									</div>
								</div>
							</div>
						</div>

						<div class="mb-2.5">
							<div class="flex w-full justify-between items-center">
								<div class="text-xs pr-2 shrink-0">
									<div class="">
										{$i18n.t('OpenAI API Version')}
									</div>
								</div>

								<div class="flex w-full">
									<div class="flex-1">
										<input
											class="w-full text-sm bg-transparent outline-hidden text-right"
											placeholder={$i18n.t('API Version')}
											bind:value={config.IMAGES_EDIT_OPENAI_API_VERSION}
										/>
									</div>
								</div>
							</div>
						</div>
					{:else if config?.IMAGE_EDIT_ENGINE === 'gemini'}
						<div class="mb-2.5">
							<div class="flex w-full justify-between items-center">
								<div class="text-xs pr-2 shrink-0">
									<div class="">
										{$i18n.t('Gemini Base URL')}
									</div>
								</div>

								<div class="flex w-full">
									<div class="flex-1">
										<input
											class="w-full text-sm bg-transparent outline-hidden text-right"
											placeholder={$i18n.t('API Base URL')}
											bind:value={config.IMAGES_EDIT_GEMINI_API_BASE_URL}
										/>
									</div>
								</div>
							</div>
						</div>

						<div class="mb-2.5">
							<div class="flex w-full justify-between items-center">
								<div class="text-xs pr-2 shrink-0">
									<div class="">
										{$i18n.t('Gemini API Key')}
									</div>
								</div>

								<div class="flex w-full">
									<div class="flex-1">
										<SensitiveInput
											inputClassName="text-right w-full"
											placeholder={$i18n.t('API Key')}
											bind:value={config.IMAGES_EDIT_GEMINI_API_KEY}
											required={true}
										/>
									</div>
								</div>
							</div>
						</div>
					{/if}
				</div>
			</div>
		{/if}
	</div>

	<div class="flex justify-end pt-3 text-sm font-medium">
		<button
			class="px-3.5 py-1.5 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-full flex flex-row space-x-1 items-center {loading
				? ' cursor-not-allowed'
				: ''}"
			type="submit"
			disabled={loading}
		>
			{$i18n.t('Save')}

			{#if loading}
				<div class="ml-2 self-center">
					<Spinner />
				</div>
			{/if}
		</button>
	</div>
</form>
