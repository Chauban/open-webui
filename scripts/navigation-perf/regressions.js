// Tabbit nodejs program. Run only on the loopback fixture, after the production build.
if (!page.url().startsWith('http://127.0.0.1:5099/')) throw new Error('Fixture origin required');
const checks = (globalThis.fixtureChecks = []);
const errors = [];
const errorHandler = (e) => errors.push(e.message);
page.on('pageerror', errorHandler);
const control = async (body) =>
	page.evaluate(
		async (body) =>
			(
				await fetch('/__fixture', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify(body)
				})
			).json(),
		body
	);
const home = async () => {
	if (!page.url().endsWith('/me/writing'))
		await page.locator('a[href="/me/writing"]:visible').first().click();
	await page.waitForURL('**/me/writing');
	await page.getByText('隔离验收 long', { exact: true }).waitFor();
};
const entry = (key) =>
	page
		.getByText(`隔离验收 ${key}`, { exact: true })
		.locator('..')
		.locator('..')
		.locator('..')
		.getByRole('button', { name: /继续写作|查看批改|查看提交|修改后重交|开始写作/ });
const editor = () => page.locator('.ProseMirror:not(#chat-input):visible');
const open = async (key) => {
	await home();
	await entry(key).click();
	await page.waitForURL(`**/assignments/${key}/write`);
	await editor().waitFor();
};
try {
	if (!['after-reload', 'remaining'].includes(globalThis.regressionPhase)) {
		// Cleanup only this synthetic student's leftovers from an interrupted fixture run.
		await page.evaluate(() => {
			for (const key of Object.keys(localStorage))
				if (key.startsWith('writing-backup:perf-student:')) localStorage.removeItem(key);
		});
		await control({
			aggregate: true,
			full_context: false,
			delays: {},
			tags_delay_ms: 400,
			save_fail: false,
			hidden: [],
			denied: false,
			extra: ['returned', 'illustrated']
		});
		await home();
		await control({ delays: { 'v1/assignments/ordinary/workspace': 1800 } });
		const late = page.waitForResponse((r) => r.url().endsWith('/assignments/ordinary/workspace'));
		await entry('ordinary').click();
		await page.waitForURL('**/assignments/ordinary/write');
		await home();
		await entry('long').click();
		await editor().waitFor();
		await late;
		await page.waitForFunction(
			() => document.querySelector('.ProseMirror:not(#chat-input)')?.textContent.length > 19000
		);
		if (!page.url().includes('/long/'))
			throw new Error('Late response changed the active assignment');
		checks.push('A→home→B: late A response does not replace B draft or conversation');

		await control({ delays: {}, tags_delay_ms: 3000 });
		await home();
		await entry('ordinary').evaluate((el) =>
			el.addEventListener('click', () => (window.__fixtureClick = performance.now()), {
				once: true,
				capture: true
			})
		);
		await entry('ordinary').click();
		await editor().waitFor();
		const ready = await page.evaluate(() => performance.now() - window.__fixtureClick);
		if (ready > 1500) throw new Error(`Slow tags blocked workspace: ${ready}`);
		checks.push({ slow_tags_ready_ms: ready });

		await home();
		await control({ tags_delay_ms: 400, delays: { 'v1/chats/chat-ordinary': 1200 } });
		const chatRequest = page.waitForRequest(
			(r) => r.url().endsWith('/chats/chat-ordinary') && r.method() === 'GET'
		);
		await entry('ordinary').click();
		await chatRequest;
		await control({
			event: {
				chat_id: 'chat-ordinary',
				message_id: 'ordinary-message-9',
				data: {
					type: 'chat:message',
					data: { content: '实时事件保留：较早历史不得覆盖这条消息。' }
				}
			}
		});
		await page.getByText('实时事件保留：较早历史不得覆盖这条消息。', { exact: true }).waitFor();
		checks.push('Socket event during delayed history survives initial state application');
		if (globalThis.regressionPhase === 'core-only') return { checks, errors };

		await control({ delays: {}, save_fail: true });
		await open('ordinary');
		await editor().fill('这是隔离环境中的未同步修改。'.repeat(20));
		await page.getByRole('button', { name: '重试保存', exact: true }).waitFor();
		await page.locator('#chat-input').fill('这是一条未发送的隔离测试消息');
		await page.waitForFunction(() =>
			sessionStorage.getItem('chat-input-chat-ordinary')?.includes('未发送的隔离测试消息')
		);
		return { checks, errors, needsNativeReload: true };
	}
	if (globalThis.regressionPhase !== 'remaining') {
		await page.getByRole('button', { name: '恢复此稿并保存', exact: true }).waitFor();
		if (!(await editor().textContent()).includes('这是一份用于性能验收'))
			throw new Error('Backup overwrote server draft');
		if (!(await page.locator('#chat-input').textContent()).includes('未发送的隔离测试消息'))
			throw new Error('Unsent input lost');
		const server = await page.evaluate(async () => (await fetch('/__fixture')).json());
		if (
			server.requests.some(
				(r) =>
					r.method === 'POST' && (r.path.endsWith('/readings') || r.path.includes('completions'))
			)
		)
			throw new Error('Restoration started a model');
		checks.push(
			'Save failure preserves backup; reload keeps server draft and unsent input; no model call'
		);
	}
	await page.evaluate(() => {
		for (const key of Object.keys(localStorage))
			if (key.startsWith('writing-backup:perf-student:')) localStorage.removeItem(key);
		sessionStorage.removeItem('chat-input-chat-ordinary');
	});
	await control({ save_fail: false });
	await home();

	await control({
		hidden: ['ordinary'],
		notification: {
			type: 'assignment_visibility_changed',
			payload: { assignment_id: 'ordinary', hidden: true }
		}
	});
	await page.getByText('隔离验收 ordinary', { exact: true }).waitFor({ state: 'hidden' });
	await control({
		hidden: [],
		notification: {
			type: 'assignment_visibility_changed',
			payload: { assignment_id: 'ordinary', hidden: false }
		}
	});
	await page.getByText('隔离验收 ordinary', { exact: true }).waitFor();
	checks.push('Visibility event refreshes home even when unread counts stay unchanged');
	await control({ denied: true });
	await entry('ordinary').click();
	await page
		.locator('main')
		.getByText(/Assignment access denied/)
		.waitFor();
	if (await editor().count()) throw new Error('Denied workspace still exposes editor');
	await control({ denied: false });
	await home();
	checks.push('Permission refusal exposes no cached draft');

	await page.evaluate(() => {
		window.__fixtureFetch = window.fetch;
		window.__fixtureReads = [];
		window.fetch = (...args) => {
			window.__fixtureReads.push(String(args[0]));
			return window.__fixtureFetch(...args);
		};
	});
	try {
		await control({ reconnect: true });
		await page.waitForFunction(
			() => window.__fixtureReads.some((url) => url.endsWith('/me/writing/home')),
			null,
			{ timeout: 45000 }
		);
	} finally {
		await page.evaluate(() => {
			window.fetch = window.__fixtureFetch;
			delete window.__fixtureFetch;
		});
	}
	await page.getByText('隔离验收 ordinary', { exact: true }).waitFor();
	checks.push('Socket transport reconnect revalidates home');

	await open('illustrated');
	await editor().locator('table').waitFor();
	await editor().locator('figure').waitFor();
	checks.push('Image reference, caption and table restore with text');
	await home();
	await page.setViewportSize({ width: 390, height: 844 });
	await entry('ordinary').click();
	await page.getByRole('button', { name: '作业内容', exact: true }).click();
	await editor().waitFor();
	await page.waitForFunction(
		() =>
			document.querySelector('.ProseMirror:not(#chat-input)')?.getAttribute('contenteditable') ===
			'true'
	);
	const mobile = await page.evaluate(() => ({
		width: innerWidth,
		scroll: document.documentElement.scrollWidth,
		editable: document
			.querySelector('.ProseMirror:not(#chat-input)')
			?.getAttribute('contenteditable')
	}));
	if (mobile.scroll > mobile.width || mobile.editable !== 'true')
		throw new Error(`Mobile state: ${JSON.stringify(mobile)}`);
	checks.push({ mobile });
	const screenshot = await page.screenshot({ fullPage: false });
	return { checks, errors, screenshot };
} catch (error) {
	return {
		checks,
		errors,
		failure: String(error),
		url: page.url(),
		view: await tabbit.observe({ frames: 'none', maxChars: 3000 })
	};
} finally {
	page.off('pageerror', errorHandler);
}
