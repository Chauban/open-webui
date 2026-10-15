// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest';

import { UPLOAD_MAX_EDGE, shrinkImageForUpload } from './text-import';

const photo = (name: string, size: number, type = 'image/jpeg') => {
	const file = new File(['x'], name, { type, lastModified: 1 });
	Object.defineProperty(file, 'size', { value: size });
	return file;
};

const drawn: Array<{ width: number; height: number; fill: string }> = [];

const mockCanvas = (blobSize: number) => {
	// 画布尺寸在取 context 之前就设好了,取的时候记下来即可。
	vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(function (
		this: HTMLCanvasElement
	) {
		const { width, height } = this;
		return {
			fillStyle: '',
			fillRect() {
				drawn.push({ width, height, fill: this.fillStyle });
			},
			drawImage() {}
		} as unknown as CanvasRenderingContext2D;
	} as never);
	vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((callback, type) => {
		const blob = new Blob(['jpeg']);
		Object.defineProperty(blob, 'size', { value: blobSize });
		expect(type).toBe('image/jpeg');
		callback(blob);
	});
};

afterEach(() => {
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
	drawn.length = 0;
});

test('手机大图在上传前按 EXIF 摆正、缩到长边 1600、白底 JPEG 0.85,保留文件名', async () => {
	const createImageBitmap = vi
		.fn()
		.mockResolvedValue({ width: 3024, height: 4032, close: vi.fn() });
	vi.stubGlobal('createImageBitmap', createImageBitmap);
	mockCanvas(600_000);

	const original = photo('IMG_0001.jpg', 4_000_000);
	const shrunk = await shrinkImageForUpload(original);

	expect(createImageBitmap).toHaveBeenCalledWith(original, { imageOrientation: 'from-image' });
	expect(UPLOAD_MAX_EDGE).toBe(1600);
	expect(drawn).toEqual([{ width: 1200, height: 1600, fill: '#ffffff' }]);
	expect(shrunk).not.toBe(original);
	expect(shrunk.name).toBe('IMG_0001.jpg');
	expect(shrunk.type).toBe('image/jpeg');
});

test('本来就小的图、读不了的图、不认识的格式都原样上传', async () => {
	const small = photo('scan.png', 800_000, 'image/png');
	vi.stubGlobal(
		'createImageBitmap',
		vi.fn().mockResolvedValue({ width: 1200, height: 1600, close: vi.fn() })
	);
	expect(await shrinkImageForUpload(small)).toBe(small);

	const heic = photo('IMG_0002.heic', 3_000_000, 'image/heic');
	expect(await shrinkImageForUpload(heic)).toBe(heic);

	vi.stubGlobal('createImageBitmap', vi.fn().mockRejectedValue(new Error('cannot decode')));
	const broken = photo('IMG_0003.jpg', 4_000_000);
	expect(await shrinkImageForUpload(broken)).toBe(broken);
});
