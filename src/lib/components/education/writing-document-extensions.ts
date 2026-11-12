import { Extension, Mark, Node, mergeAttributes } from '@tiptap/core';
import { Fragment, Slice } from '@tiptap/pm/model';
import { AllSelection, Plugin } from '@tiptap/pm/state';
import {
	extractImportImages,
	getWritingMaterialAsset,
	readWritingImage
} from '$lib/apis/education';
import { textDocument } from '$lib/utils/writing-document';
import { writingAlignment } from '$lib/utils/writing-paste';

type Options = {
	t: (key: string) => string;
	sessionId: () => string;
	submissionId?: () => string | null;
	imageReading: () => boolean;
	onTranscription?: (metadata: Record<string, string>) => void;
};

const buttonClass =
	'rounded px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800 focus-visible:outline';

const storedAttributes = (defaults: Record<string, unknown>) =>
	Object.fromEntries(
		Object.entries(defaults).map(([key, value]) => [
			key,
			{
				default: value,
				parseHTML: (element: HTMLElement) => {
					try {
						return JSON.parse(element.getAttribute('data-writing-attrs') ?? '{}')[key] ?? value;
					} catch {
						return value;
					}
				},
				renderHTML: () => ({})
			}
		])
	);

function showImage(src: string, label: string, t: Options['t']) {
	const dialog = document.createElement('dialog');
	dialog.className = 'max-w-[95vw] max-h-[95vh] rounded-xl bg-white p-3 dark:bg-gray-900';
	const close = document.createElement('button');
	close.textContent = t('Close');
	close.className = buttonClass;
	close.onclick = () => dialog.close();
	const img = document.createElement('img');
	img.src = src;
	img.alt = label;
	img.className = 'max-h-[85vh] max-w-full object-contain';
	dialog.append(close, img);
	dialog.onclose = () => dialog.remove();
	document.body.append(dialog);
	dialog.showModal();
	return dialog;
}

export function writingAssetView(
	root: HTMLElement,
	options: { submissionId?: string | null; t: Options['t'] }
) {
	let stopped = false;
	const urls: string[] = [];
	const dialogs: HTMLDialogElement[] = [];
	for (const reading of root.querySelectorAll<HTMLElement>('[data-reading-kind]')) {
		reading.querySelector('summary')!.textContent = options.t(
			reading.dataset.readingKind === 'native' ? '查看文字层' : '查看识别文字'
		);
	}
	for (const note of root.querySelectorAll<HTMLButtonElement>('[data-writing-note]')) {
		note.setAttribute('aria-label', `${options.t('脚注／注释')} ${note.textContent}`);
		note.onclick = () => {
			const dialog = document.createElement('dialog');
			dialog.className = 'w-[min(90vw,32rem)] rounded-xl bg-white p-5 dark:bg-gray-900';
			const text = document.createElement('p');
			text.className = 'whitespace-pre-wrap break-words';
			text.textContent = note.dataset.writingNote ?? '';
			const close = document.createElement('button');
			close.className = buttonClass;
			close.textContent = options.t('Close');
			close.onclick = () => dialog.close();
			dialog.append(text, close);
			dialog.onclose = () => dialog.remove();
			document.body.append(dialog);
			dialogs.push(dialog);
			dialog.showModal();
		};
	}
	for (const figure of root.querySelectorAll<HTMLElement>('[data-writing-image]')) {
		const img = figure.querySelector('img')!;
		getWritingMaterialAsset(
			localStorage.token,
			figure.dataset.materialId!,
			`${figure.dataset.blockId}.jpg`,
			options.submissionId
		)
			.then((blob) => {
				if (stopped) return;
				const url = URL.createObjectURL(blob);
				urls.push(url);
				img.src = url;
				img.onclick = () => {
					dialogs.push(showImage(url, img.alt, options.t));
				};
				img.tabIndex = 0;
				img.onkeydown = (event) => {
					if (event.key === 'Enter') dialogs.push(showImage(url, img.alt, options.t));
				};
			})
			.catch(() => {
				if (!stopped) img.alt = options.t('图片加载失败，请重新打开稿件。');
			});
	}
	return {
		destroy() {
			stopped = true;
			urls.forEach((url) => URL.revokeObjectURL(url));
			dialogs.forEach((dialog) => dialog.remove());
		}
	};
}

export function writingExtensions(options: Options) {
	const t = options.t;
	const image = Node.create({
		name: 'writingImage',
		group: 'block',
		content: 'inline*',
		draggable: true,
		addAttributes: () =>
			storedAttributes({
				materialId: '',
				blockId: '',
				width: 100,
				alt: '',
				transcription: '',
				transcriptionEdited: false,
				nativeText: '',
				nativeTextEdited: false,
				readStatus: '',
				readDetail: ''
			}),
		parseHTML: () => [{ tag: 'figure[data-writing-image]' }],
		renderHTML: ({ node }) => [
			'figure',
			{
				'data-writing-attrs': JSON.stringify(node.attrs),
				'data-writing-image': '',
				'data-material-id': node.attrs.materialId,
				'data-block-id': node.attrs.blockId,
				style: `width:${node.attrs.width}%;margin:1em auto`
			},
			['figcaption', 0]
		],
		addNodeView() {
			return ({ node: initial, editor, getPos }) => {
				let node = initial;
				let disposed = false;
				let assetKey = '';
				let imageUrl = '';
				let request = 0;
				const dom = document.createElement('figure');
				dom.className = 'writing-figure my-5 mx-auto';
				const controls = document.createElement('div');
				controls.contentEditable = 'false';
				controls.className = 'mb-2 flex flex-wrap justify-center gap-1';
				const img = document.createElement('img');
				img.className = 'mx-auto max-w-full cursor-zoom-in rounded object-contain';
				img.draggable = false;
				img.onclick = () => {
					if (imageUrl) showImage(imageUrl, node.attrs.alt, t);
				};
				const status = document.createElement('p');
				status.className = 'text-center text-xs text-gray-500';
				status.contentEditable = 'false';
				const readingNotice = document.createElement('p');
				readingNotice.className = 'mt-2 text-xs text-amber-700 dark:text-amber-300';
				readingNotice.contentEditable = 'false';
				const contentDOM = document.createElement('figcaption');
				contentDOM.className = 'mt-2 min-h-5 text-center text-sm text-gray-600 dark:text-gray-300';
				contentDOM.setAttribute('aria-label', t('图注'));
				const details = document.createElement('details');
				details.contentEditable = 'false';
				details.className = 'mt-2 text-sm';
				const summary = document.createElement('summary');
				summary.className = 'cursor-pointer text-xs text-gray-500';
				summary.textContent = t('查看／校对识别文字');
				const input = document.createElement('textarea');
				input.className = 'mt-2 min-h-28 w-full rounded border bg-transparent p-2 text-sm';
				input.setAttribute('aria-label', t('图片识别文字'));
				input.maxLength = 200000;
				const hint = document.createElement('p');
				hint.className = 'my-1 text-xs text-gray-500';
				hint.textContent = t('识别文字仅供核对，不会自动加入正文。');
				const setAttrs = (attrs: Record<string, unknown>) => {
					const pos = getPos();
					if (typeof pos === 'number' && editor.isEditable)
						editor.view.dispatch(
							editor.state.tr.setNodeMarkup(pos, undefined, { ...node.attrs, ...attrs })
						);
				};
				input.onchange = () =>
					setAttrs(
						node.attrs.nativeText && (!options.imageReading() || !node.attrs.transcription)
							? { nativeText: input.value, nativeTextEdited: true }
							: { transcription: input.value, transcriptionEdited: true }
					);
				function button(
					label: string,
					callback: () => void | Promise<void>,
					parent: HTMLElement = controls
				) {
					const el = document.createElement('button');
					el.type = 'button';
					el.className = buttonClass;
					el.textContent = t(label);
					el.onclick = async () => {
						el.disabled = true;
						try {
							await callback();
						} catch {
							status.textContent = t('操作失败，请重试。');
						} finally {
							el.disabled = false;
						}
					};
					parent.append(el);
					return el;
				}
				const width = document.createElement('select');
				width.className = buttonClass + ' bg-transparent';
				width.setAttribute('aria-label', t('图片宽度'));
				for (const value of [40, 70, 100]) {
					const option = new Option(`${value}%`, String(value));
					width.add(option);
				}
				width.onchange = () => setAttrs({ width: Number(width.value) });
				controls.append(width);
				function move(direction: -1 | 1) {
					const pos = getPos();
					if (typeof pos !== 'number') return;
					const resolved = editor.state.doc.resolve(pos);
					const index = resolved.index();
					const siblingIndex = index + direction;
					if (siblingIndex < 0 || siblingIndex >= resolved.parent.childCount) return;
					const sibling = resolved.parent.child(siblingIndex);
					const from = direction < 0 ? pos - sibling.nodeSize : pos;
					editor.view.dispatch(
						editor.state.tr.replaceWith(
							from,
							from + node.nodeSize + sibling.nodeSize,
							Fragment.fromArray(direction < 0 ? [node, sibling] : [sibling, node])
						)
					);
				}
				button('上移', () => move(-1));
				button('下移', () => move(1));
				button('删除图片', () => {
					const pos = getPos();
					if (typeof pos === 'number')
						editor.commands.deleteRange({ from: pos, to: pos + node.nodeSize });
				});
				const replaceInput = document.createElement('input');
				replaceInput.type = 'file';
				replaceInput.accept = 'image/png,image/jpeg,image/webp';
				replaceInput.hidden = true;
				replaceInput.onchange = async () => {
					const file = replaceInput.files?.[0];
					if (!file) return;
					status.textContent = t('上传中…');
					try {
						const result = await extractImportImages(
							localStorage.token,
							options.sessionId(),
							[file],
							'reference'
						);
						if (!disposed) {
							setAttrs({ ...result.content_json.content![0].attrs, width: node.attrs.width });
							status.textContent = '';
						}
					} catch {
						status.textContent = t('图片上传失败，请重试。');
					}
					replaceInput.value = '';
				};
				button('替换图片', () => replaceInput.click());
				controls.append(replaceInput);
				const recognize = button(
					'读取参考图片',
					async () => {
						const ref = `${node.attrs.materialId}/${node.attrs.blockId}`;
						status.textContent = t('正在识别图片…');
						const result = await readWritingImage(
							localStorage.token,
							options.sessionId(),
							node.attrs.materialId,
							node.attrs.blockId
						);
						if (disposed || ref !== `${node.attrs.materialId}/${node.attrs.blockId}`) return;
						const block = result.blocks[0];
						setAttrs({
							materialId: result.material_id,
							transcription: block.text,
							transcriptionEdited: false,
							readStatus: block.status,
							readDetail: block.detail
						});
						status.textContent = block.text
							? ''
							: t(
									block.status === 'read'
										? '未发现可提取文字，原图已保留。'
										: '未能读出图片文字，可重试或手动补充正文。'
								);
						details.open = true;
					},
					details
				);
				const insert = button(
					'将这些文字插入正文',
					() => {
						const pos = getPos();
						if (typeof pos !== 'number' || !input.value.trim()) return;
						options.onTranscription?.({
							material_id: node.attrs.materialId,
							block_id: node.attrs.blockId
						});
						editor
							.chain()
							.focus()
							.insertContentAt(pos + node.nodeSize, textDocument(input.value).content!)
							.run();
					},
					details
				);
				details.prepend(summary, hint, input);
				dom.append(controls, img, status, contentDOM, readingNotice, details);
				function render() {
					dom.style.width = `${node.attrs.width}%`;
					controls.hidden = !editor.isEditable;
					readingNotice.textContent =
						options.imageReading() && node.attrs.readStatus === 'unreadable'
							? t(node.attrs.readDetail || '未能读出图片文字，可重试或手动补充正文。')
							: '';
					width.value = String(node.attrs.width);
					const native =
						node.attrs.nativeText && (!options.imageReading() || !node.attrs.transcription);
					summary.textContent = t(native ? '查看／编辑文字层' : '查看／校对识别文字');
					details.hidden =
						!options.imageReading() && !node.attrs.transcription && !node.attrs.nativeText;
					recognize.hidden = !editor.isEditable || !options.imageReading();
					insert.hidden = !editor.isEditable || (!options.imageReading() && !native);
					input.readOnly = !editor.isEditable || (!options.imageReading() && !native);
					if (document.activeElement !== input)
						input.value = native ? node.attrs.nativeText : node.attrs.transcription;
					img.alt = node.attrs.alt || t('稿件图片');
					const key = `${node.attrs.materialId}/${node.attrs.blockId}`;
					if (assetKey === key) return;
					assetKey = key;
					const current = ++request;
					status.textContent = t('正在加载图片…');
					getWritingMaterialAsset(
						localStorage.token,
						node.attrs.materialId,
						node.attrs.blockId + '.jpg',
						options.submissionId?.()
					)
						.then((blob) => {
							if (disposed || current !== request) return;
							if (imageUrl) URL.revokeObjectURL(imageUrl);
							imageUrl = URL.createObjectURL(blob);
							img.src = imageUrl;
							status.textContent = '';
						})
						.catch(() => {
							if (!disposed && current === request)
								status.textContent = t('图片加载失败，请重新打开稿件。');
						});
				}
				render();
				editor.on('update', render);
				return {
					dom,
					contentDOM,
					update(next) {
						if (next.type !== node.type) return false;
						node = next;
						render();
						return true;
					},
					stopEvent(event) {
						return (
							!contentDOM.contains(event.target as globalThis.Node) && event.target !== contentDOM
						);
					},
					ignoreMutation(mutation) {
						return mutation.type !== 'selection' && !contentDOM.contains(mutation.target);
					},
					destroy() {
						disposed = true;
						editor.off('update', render);
						if (imageUrl) URL.revokeObjectURL(imageUrl);
					}
				};
			};
		}
	});
	const note = Node.create({
		name: 'writingNote',
		group: 'inline',
		inline: true,
		atom: true,
		addAttributes: () =>
			storedAttributes({ materialId: '', blockId: '', label: '', note: '', kind: 'footnote' }),
		parseHTML: () => [{ tag: 'sup[data-writing-note]' }],
		renderHTML: ({ node }) => [
			'sup',
			{
				'data-writing-note': '',
				'data-writing-attrs': JSON.stringify(node.attrs),
				title: node.attrs.note
			},
			`[${node.attrs.label}]`
		],
		addNodeView:
			() =>
			({ node: initial, editor, getPos }) => {
				let node = initial;
				const dom = document.createElement('sup');
				dom.className = 'cursor-pointer text-sky-700';
				dom.contentEditable = 'false';
				const render = () => {
					dom.textContent = `[${node.attrs.label}]`;
					dom.title = node.attrs.note;
				};
				dom.onclick = () => {
					const dialog = document.createElement('dialog');
					dialog.className = 'w-[min(90vw,32rem)] rounded-xl bg-white p-5 dark:bg-gray-900';
					const label = document.createElement('label');
					label.textContent = t('脚注／注释');
					const input = document.createElement('textarea');
					input.className = 'mt-3 min-h-32 w-full rounded border bg-transparent p-2';
					input.value = node.attrs.note;
					input.readOnly = !editor.isEditable;
					label.append(input);
					const save = document.createElement('button');
					save.className = buttonClass;
					save.textContent = t(editor.isEditable ? 'Save' : 'Close');
					save.onclick = () => {
						const pos = getPos();
						if (editor.isEditable && typeof pos === 'number')
							editor.view.dispatch(
								editor.state.tr.setNodeMarkup(pos, undefined, { ...node.attrs, note: input.value })
							);
						dialog.close();
					};
					dialog.append(label, save);
					dialog.onclose = () => dialog.remove();
					document.body.append(dialog);
					dialog.showModal();
				};
				render();
				return {
					dom,
					update(next) {
						if (next.type !== node.type) return false;
						node = next;
						render();
						return true;
					}
				};
			}
	});
	const placeholder = Node.create({
		name: 'writingPlaceholder',
		group: 'block',
		atom: true,
		addAttributes: () => storedAttributes({ materialId: '', blockId: '', label: '' }),
		parseHTML: () => [{ tag: 'aside[data-writing-placeholder]' }],
		renderHTML: ({ node }) => [
			'aside',
			{
				'data-writing-placeholder': '',
				'data-writing-attrs': JSON.stringify(node.attrs),
				class: 'my-3 border-l-2 border-amber-400 pl-3 text-sm'
			},
			t(node.attrs.label)
		]
	});
	const alignment = Extension.create({
		name: 'writingAlignment',
		addGlobalAttributes: () => [
			{
				types: ['paragraph', 'heading'],
				attributes: {
					textAlign: {
						default: null,
						parseHTML: writingAlignment,
						renderHTML: (attrs) =>
							attrs.textAlign ? { style: `text-align:${attrs.textAlign}` } : {}
					}
				}
			}
		]
	});
	const clipboard = Extension.create({
		name: 'writingClipboard',
		addProseMirrorPlugins: () => [
			new Plugin({
				props: {
					transformCopied: (slice, view) => {
						if (!(view.state.selection instanceof AllSelection)) return slice;
						// Ctrl+A includes the document's outer paragraph boundaries. Copy
						// them as text-selection edges so pasting doesn't invent a new line.
						// Inner paragraphs and non-paragraph blocks keep their structure.
						return new Slice(
							slice.content,
							slice.content.firstChild?.type.name === 'paragraph' ? 1 : slice.openStart,
							slice.content.lastChild?.type.name === 'paragraph' ? 1 : slice.openEnd
						);
					}
				}
			})
		]
	});
	return [
		image,
		note,
		placeholder,
		alignment,
		clipboard,
		...(['superscript', 'subscript'] as const).map((name) =>
			Mark.create({
				name,
				parseHTML: () => [{ tag: name === 'superscript' ? 'sup' : 'sub' }],
				renderHTML: ({ HTMLAttributes }) => [
					name === 'superscript' ? 'sup' : 'sub',
					mergeAttributes(HTMLAttributes),
					0
				]
			})
		)
	];
}
