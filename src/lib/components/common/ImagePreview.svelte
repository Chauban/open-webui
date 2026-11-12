<script lang="ts">
	import { getContext } from 'svelte';
	import Modal from './Modal.svelte';

	import { toast } from 'svelte-sonner';
	import fileSaver from 'file-saver';
	const { saveAs } = fileSaver;

	import { WEBUI_BASE_URL } from '$lib/constants';
	import PanzoomContainer from '$lib/components/common/PanzoomContainer.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	export let show = false;
	export let src = '';
	export let alt = '';

	const i18n = getContext('i18n');
</script>

<Modal
	bind:show
	size="full"
	className="rw-image-viewer"
	containerClassName="rw-image-overlay"
	ariaLabel={alt || $i18n.t('Image preview')}
>
	<div class=" absolute left-0 w-full flex justify-between select-none z-20">
		<div>
			<button
				class=" p-5"
				aria-label={$i18n.t('Close')}
				on:pointerdown={(e) => {
					e.stopImmediatePropagation();
					e.preventDefault();
					show = false;
				}}
				on:click={(e) => {
					show = false;
				}}
			>
				<XMark className={'size-6'} />
			</button>
		</div>

		<div>
			<button
				aria-label={$i18n.t('Download')}
				class=" p-5 z-999"
				on:click={() => {
					if (src.startsWith('data:image/')) {
						const base64Data = src.split(',')[1];
						const blob = new Blob([Uint8Array.from(atob(base64Data), (c) => c.charCodeAt(0))], {
							type: 'image/png'
						});

						const mimeType = blob.type || 'image/png';
						// create file name based on the MIME type, alt should be a valid file name with extension
						const fileName = `${$i18n
							.t('Generated Image')
							.toLowerCase()
							.replace(/ /g, '_')}.${mimeType.split('/')[1]}`;

						// Use FileSaver to save the blob
						saveAs(blob, fileName);
						return;
					} else if (src.startsWith('blob:')) {
						// Handle blob URLs
						fetch(src)
							.then((response) => response.blob())
							.then((blob) => {
								// detect the MIME type from the blob
								const mimeType = blob.type || 'image/png';

								// Create a new Blob with the correct MIME type
								const blobWithType = new Blob([blob], { type: mimeType });

								// create file name based on the MIME type, alt should be a valid file name with extension
								const fileName = `${$i18n
									.t('Generated Image')
									.toLowerCase()
									.replace(/ /g, '_')}.${mimeType.split('/')[1]}`;

								// Use FileSaver to save the blob
								saveAs(blobWithType, fileName);
							})
							.catch((error) => {
								console.error('Error downloading blob:', error);
							});
						return;
					} else if (
						src.startsWith('/') ||
						src.startsWith('http://') ||
						src.startsWith('https://')
					) {
						// Handle remote URLs
						const backendOrigin = new URL(WEBUI_BASE_URL || '/', window.location.origin).origin;
						const isBackendUrl = new URL(src, window.location.origin).origin === backendOrigin;

						fetch(
							src,
							isBackendUrl && localStorage.token
								? { headers: { Authorization: `Bearer ${localStorage.token}` } }
								: undefined
						)
							.then((response) => {
								if (!response.ok) {
									throw new Error(`Failed to download image: ${response.status}`);
								}
								return response.blob();
							})
							.then((blob) => {
								// detect the MIME type from the blob
								const mimeType = blob.type || 'image/png';

								// Create a new Blob with the correct MIME type
								const blobWithType = new Blob([blob], { type: mimeType });

								// create file name based on the MIME type, alt should be a valid file name with extension
								const fileName = `${$i18n
									.t('Generated Image')
									.toLowerCase()
									.replace(/ /g, '_')}.${mimeType.split('/')[1]}`;

								// Use FileSaver to save the blob
								saveAs(blobWithType, fileName);
							})
							.catch((error) => {
								console.error('Error downloading remote image:', error);
								toast.error($i18n.t('Failed to download image'));
							});
						return;
					}
				}}
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 20 20"
					fill="currentColor"
					class="w-6 h-6"
				>
					<path
						d="M10.75 2.75a.75.75 0 0 0-1.5 0v8.614L6.295 8.235a.75.75 0 1 0-1.09 1.03l4.25 4.5a.75.75 0 0 0 1.09 0l4.25-4.5a.75.75 0 0 0-1.09-1.03l-2.955 3.129V2.75Z"
					/>
					<path
						d="M3.5 12.75a.75.75 0 0 0-1.5 0v2.5A2.75 2.75 0 0 0 4.75 18h10.5A2.75 2.75 0 0 0 18 15.25v-2.5a.75.75 0 0 0-1.5 0v2.5c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25v-2.5Z"
					/>
				</svg>
			</button>
		</div>
	</div>
	<PanzoomContainer className="flex h-full max-h-full justify-center items-center z-0">
		<img {src} {alt} class=" mx-auto h-full object-scale-down select-none" draggable="false" />
	</PanzoomContainer>
</Modal>
