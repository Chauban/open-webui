// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest';
import { disclosure } from './disclosure';

afterEach(() => {
	vi.unstubAllGlobals();
});

test('快速反向展开会取消旧动画，并保留表单节点', () => {
	vi.stubGlobal('matchMedia', () => ({ matches: false }));
	const node = document.createElement('div');
	const input = document.createElement('input');
	input.value = '未保存内容';
	node.append(input);
	node.getBoundingClientRect = () => ({ height: 160 }) as DOMRect;
	const animations: Array<{ cancel: ReturnType<typeof vi.fn>; onfinish?: () => void }> = [];
	node.animate = vi.fn(() => {
		const animation = { cancel: vi.fn() };
		animations.push(animation);
		return animation as unknown as Animation;
	});
	const action = disclosure(node, true);
	action.update(false);
	expect(node.inert).toBe(true);
	expect(node.hidden).toBe(false);
	action.update(true);
	expect(animations[0].cancel).toHaveBeenCalled();
	animations[1].onfinish?.();
	expect(node.hidden).toBe(false);
	expect(node.inert).toBe(false);
	expect(node.firstChild).toBe(input);
	expect(input.value).toBe('未保存内容');
	expect(node.style.overflow).toBe('');
	action.destroy();
});

test('减少动态效果时立即收起，不创建动画', () => {
	vi.stubGlobal('matchMedia', () => ({ matches: true }));
	const node = document.createElement('div');
	node.animate = vi.fn();
	const action = disclosure(node, true);
	action.update(false);
	expect(node.hidden).toBe(true);
	expect(node.getAttribute('aria-hidden')).toBe('true');
	expect(node.animate).not.toHaveBeenCalled();
	action.destroy();
});
