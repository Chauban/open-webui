// Execute through tabbit-cli nodejs on the owned loopback fixture tab.
// Set globalThis.perfScenario and globalThis.perfPhase before executing.
const scenario = globalThis.perfScenario || 'ordinary';
if (!page.url().startsWith('http://127.0.0.1:5099/')) throw new Error('Fixture origin required');
const phase = globalThis.perfPhase || 'before';
const count =
	{ empty: 0, pending: 0, unread: 0, scratch: 0, ordinary: 10, long: 50, stress: 200 }[scenario] ??
	10;
const samples = [];
const errors = [];
const failed = [];
const onError = (e) => errors.push(e.message);
const onFailed = (request) =>
	failed.push({ url: new URL(request.url()).pathname, error: request.failure()?.errorText });
page.on('pageerror', onError);
page.on('requestfailed', onFailed);
if (await page.evaluate(() => document.hidden))
	throw new Error('Keep the fixture tab visible for paint timing');
const arm = async (target, kind) =>
	target.evaluate(
		(element, args) => {
			const [kind, key, count] = args;
			element.addEventListener(
				'click',
				() => {
					performance.clearResourceTimings();
					performance.setResourceTimingBufferSize(5000);
					const record = (window.__navigationPerf = {
						kind,
						key,
						start: performance.now(),
						timeOrigin: performance.timeOrigin,
						hidden: document.hidden,
						preview: null,
						ready: null,
						fresh: null,
						resources: []
					});
					const check = () => {
						const editor = [...document.querySelectorAll('.ProseMirror:not(#chat-input)')].find(
							(e) => e.getBoundingClientRect().width > 0
						);
						const list = [...document.querySelectorAll('main button')].some((e) =>
							e.textContent.includes('继续写作')
						);
						const expected = count ? `合成历史消息 ${key} ${count - 1}：` : '';
						const draft =
							editor &&
							(key === 'empty'
								? editor.textContent.length === 0
								: editor.textContent.includes('这是一份用于性能验收的合成大学写作稿件'));
						const content = kind === 'home' ? list : draft;
						if (content && record.preview === null)
							record.preview = performance.now() - record.start;
						const expectedEditable = !['running', 'generating', 'readonly'].includes(key);
						const restored =
							content &&
							(kind === 'home' ||
								editor?.getAttribute('contenteditable') === String(expectedEditable)) &&
							(kind === 'home' ||
								!count ||
								document.querySelector('[role="log"]')?.textContent.includes(expected));
						if (restored) {
							requestAnimationFrame(() => {
								record.ready = performance.now() - record.start;
								record.hiddenAtReady = document.hidden;
								record.editable = editor?.getAttribute('contenteditable');
								record.draftChars = editor?.textContent.length ?? 0;
								record.resources = performance
									.getEntriesByType('resource')
									.filter((r) => r.startTime >= record.start && r.name.includes('/api/'))
									.map((r) => ({
										path: new URL(r.name).pathname,
										start: r.startTime - record.start,
										end: r.responseEnd - record.start,
										encoded: r.encodedBodySize,
										decoded: r.decodedBodySize
									}));
								const seen = new Set();
								const needed = record.resources.filter((r) => {
									if (seen.has(r.path)) return false;
									seen.add(r.path);
									return /\/workspace$|\/home$|\/readings$|\/teaching-summary$|\/pending-draft$|\/chats\/chat-[^/]+$|\/tasks\/chat\//.test(
										r.path
									);
								});
								record.fresh = Math.max(0, ...needed.map((r) => r.end));
							});
						} else requestAnimationFrame(check);
					};
					requestAnimationFrame(check);
				},
				{ once: true, capture: true }
			);
		},
		[kind, scenario, count]
	);
for (let i = 0; i < (globalThis.perfIterations || 20); i++) {
	if (!page.url().endsWith('/me/writing')) {
		const homeLink = page.locator('a[href="/me/writing"]:visible').first();
		await arm(homeLink, 'home');
		await homeLink.click();
		await page.waitForFunction(() => window.__navigationPerf?.ready != null);
		samples.push({ ...(await page.evaluate(() => window.__navigationPerf)), iteration: i });
	}
	const row = page
		.getByText(`隔离验收 ${scenario}`, { exact: true })
		.locator('..')
		.locator('..')
		.locator('..');
	const button = row.getByRole('button', {
		name: /继续写作|查看批改|查看提交|修改后重交|开始写作/
	});
	await arm(button, 'workspace');
	await button.click();
	await page.waitForFunction(
		() => window.__navigationPerf?.kind === 'workspace' && window.__navigationPerf?.ready != null,
		null,
		{ timeout: 15000 }
	);
	samples.push({ ...(await page.evaluate(() => window.__navigationPerf)), iteration: i });
}
page.off('pageerror', onError);
page.off('requestfailed', onFailed);
return {
	phase,
	scenario,
	network: '400 ms added response delay, gzip, loopback, real production frontend',
	samples,
	errors,
	failed
};
