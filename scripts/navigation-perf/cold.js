// Separate full-document, cache-disabled measurement. Never mix with in-app P50/P95.
if (!page.url().startsWith('http://127.0.0.1:5099/')) throw new Error('Fixture origin required');
await page.setViewportSize({ width: 1658, height: 1060 });
await page.goto('http://127.0.0.1:5099/me/writing', { waitUntil: 'domcontentloaded' });
await page.getByText('隔离验收 ordinary', { exact: true }).waitFor();
const cdp = await context.newCDPSession(page);
await cdp.send('Network.enable');
await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
await page.addInitScript(() => {
	const raw = sessionStorage.getItem('__rw_cold');
	if (!raw) return;
	const start = JSON.parse(raw);
	const check = () => {
		const editor = document.querySelector('.ProseMirror:not(#chat-input)');
		if (
			editor?.getAttribute('contenteditable') === 'true' &&
			editor.textContent.includes('这是一份用于性能验收') &&
			document.querySelector('[role="log"]')?.textContent.includes('合成历史消息 ordinary 9：')
		) {
			requestAnimationFrame(
				() =>
					(window.__coldResult = {
						ms: performance.timeOrigin + performance.now() - start.time,
						timeOriginChanged: start.origin !== performance.timeOrigin,
						hidden: document.hidden
					})
			);
		} else requestAnimationFrame(check);
	};
	requestAnimationFrame(check);
});
const samples = [];
try {
	for (let i = 0; i < 3; i++) {
		await page.evaluate(() => {
			const link = document.createElement('a');
			link.href = '/assignments/ordinary/write';
			link.textContent = '整页冷启动隔离测试';
			link.setAttribute('data-sveltekit-reload', 'true');
			link.style =
				'position:fixed;top:5px;left:300px;z-index:999999;background:white;color:black;padding:10px';
			link.addEventListener(
				'click',
				() =>
					sessionStorage.setItem(
						'__rw_cold',
						JSON.stringify({
							time: performance.timeOrigin + performance.now(),
							origin: performance.timeOrigin
						})
					),
				{ once: true }
			);
			document.body.append(link);
		});
		await page.getByRole('link', { name: '整页冷启动隔离测试', exact: true }).click();
		await page.waitForFunction(() => window.__coldResult?.timeOriginChanged === true, null, {
			timeout: 30000
		});
		samples.push(await page.evaluate(() => window.__coldResult));
		await page.evaluate(() => sessionStorage.removeItem('__rw_cold'));
	}
	return {
		network:
			'API 400 ms response delay; full document; browser cache disabled; local static assets',
		samples
	};
} finally {
	await cdp.send('Network.setCacheDisabled', { cacheDisabled: false });
	await cdp.detach();
	await page.evaluate(() => sessionStorage.removeItem('__rw_cold'));
}
