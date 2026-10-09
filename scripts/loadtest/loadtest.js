/* global __ENV, __VU, __ITER */
// RightWrite 并发压测脚本（k6）
//
// 三个场景同时跑，模拟真实课堂：一部分学生在跟辅导助手对话（流式），
// 大部分学生只是开着页面（Socket.IO 长连接），另有零散的页面接口请求。
//
// 用法见同目录 README.md。

import http from 'k6/http';
import ws from 'k6/ws';
import { check, sleep } from 'k6';
import { Trend, Counter } from 'k6/metrics';

// ---------- 配置 ----------

const BASE = (__ENV.BASE_URL || 'http://localhost:8080').replace(/\/$/, '');
const WS_BASE = BASE.replace(/^http/, 'ws');
const MODEL = __ENV.MODEL || 'loadtest-mock';
const PASSWORD = __ENV.PASSWORD || '';
const EMAILS = (__ENV.EMAILS || '')
	.split(',')
	.map((s) => s.trim())
	.filter(Boolean);

const DURATION = __ENV.DURATION || '3m';
const CHAT_VUS = Number(__ENV.CHAT_VUS || 10);
const SOCKET_VUS = Number(__ENV.SOCKET_VUS || 40);
const BROWSE_RPS = Number(__ENV.BROWSE_RPS || 3);

// ---------- 自定义指标 ----------

const chatDuration = new Trend('chat_stream_duration', true);
const chatFailed = new Counter('chat_stream_failed');
const socketConnected = new Counter('socket_connected');
const socketFailed = new Counter('socket_failed');

export const options = {
	scenarios: {
		chat: {
			executor: 'constant-vus',
			vus: CHAT_VUS,
			duration: DURATION,
			exec: 'chatStream',
			tags: { scenario: 'chat' }
		},
		socket: {
			executor: 'constant-vus',
			vus: SOCKET_VUS,
			duration: DURATION,
			exec: 'socketIdle',
			tags: { scenario: 'socket' }
		},
		browse: {
			executor: 'constant-arrival-rate',
			rate: BROWSE_RPS,
			timeUnit: '1s',
			duration: DURATION,
			preAllocatedVUs: 20,
			maxVUs: 60,
			exec: 'browse',
			tags: { scenario: 'browse' }
		}
	},
	thresholds: {
		// 页面接口请求：99% 成功、p95 在 1.5 秒内
		'http_req_failed{scenario:browse}': ['rate<0.01'],
		'http_req_duration{scenario:browse}': ['p(95)<1500'],
		// 流式对话：失败数为 0（时长由 mock 的吐字节奏决定，不设阈值）
		chat_stream_failed: ['count==0'],
		socket_failed: ['count==0']
	},
	// 生产用的是 Let's Encrypt 证书，正常校验；本地自签名时用 --insecure-skip-tls-verify
	discardResponseBodies: false
};

// ---------- 登录 ----------

export function setup() {
	if (!EMAILS.length || !PASSWORD) {
		throw new Error('必须提供 EMAILS 与 PASSWORD 环境变量，见 README.md');
	}

	const tokens = [];
	for (const email of EMAILS) {
		const res = http.post(
			`${BASE}/api/v1/auths/signin`,
			JSON.stringify({ email, password: PASSWORD }),
			{ headers: { 'Content-Type': 'application/json' }, tags: { name: 'signin' } }
		);
		if (res.status !== 200) {
			throw new Error(`登录失败 ${email}：HTTP ${res.status} ${res.body}`);
		}
		const token = res.json('token');
		if (!token) {
			throw new Error(`登录返回里没有 token：${email}`);
		}
		tokens.push(token);
	}

	console.log(`已登录 ${tokens.length} 个账户，开始压测 ${BASE}`);
	return { tokens };
}

function tokenFor(data) {
	// VU 编号在各 scenario 间独立，取模复用账户
	return data.tokens[(__VU - 1) % data.tokens.length];
}

function authHeaders(token) {
	return {
		Authorization: `Bearer ${token}`,
		'Content-Type': 'application/json'
	};
}

// ---------- 场景一：流式对话 ----------

// 每个 VU 先建一个属于自己的对话：v0.11 起 /api/chat/completions 会校验 chat_id 归属，
// 编造的 id 会直接 404（2026-10-04 哈工深压测踩到）
let myChatId = null;

function ensureChat(token) {
	if (myChatId) return myChatId;
	const res = http.post(
		`${BASE}/api/v1/chats/new`,
		JSON.stringify({ chat: { title: `loadtest-${__VU}`, models: [MODEL], messages: [] } }),
		{ headers: authHeaders(token), tags: { name: 'chat_new' } }
	);
	if (res.status === 200 && res.json('id')) {
		myChatId = res.json('id');
	} else {
		console.error(`建对话失败 HTTP ${res.status}：${String(res.body).slice(0, 200)}`);
	}
	return myChatId;
}

export function chatStream(data) {
	const token = tokenFor(data);
	const chatId = ensureChat(token);
	if (!chatId) {
		chatFailed.add(1);
		sleep(5);
		return;
	}

	const payload = JSON.stringify({
		model: MODEL,
		chat_id: chatId,
		id: `loadtest-msg-${__VU}-${__ITER}-${Date.now()}`,
		stream: true,
		messages: [
			{
				role: 'user',
				content: '帮我看看这段论证的薄弱处在哪里，并说明理由。这是一次压力测试请求。'
			}
		]
	});

	const started = Date.now();
	const res = http.post(`${BASE}/api/chat/completions`, payload, {
		headers: authHeaders(token),
		timeout: '180s',
		tags: { name: 'chat_completions' }
	});
	const elapsed = Date.now() - started;

	// 带 chat_id 时服务端自己读完模型流、落库、经 Socket.IO 推送，HTTP 只回 null，
	// 所以不再检查 SSE 文本；耗时 > 3s 说明确实走完了假模型的流（mock 一次约 16s）
	const ok = check(res, {
		'对话返回 200': (r) => r.status === 200,
		走完了模型流: () => elapsed > 3000
	});

	chatDuration.add(elapsed);
	if (!ok) {
		chatFailed.add(1);
		console.error(`对话失败 HTTP ${res.status}：${String(res.body).slice(0, 300)}`);
	}

	// 学生看完回复、思考、再问下一句
	sleep(Number(__ENV.CHAT_THINK_SEC || 8));
}

// ---------- 场景二：挂着页面的 Socket.IO 连接 ----------

export function socketIdle(data) {
	const token = tokenFor(data);
	const url = `${WS_BASE}/ws/socket.io/?EIO=4&transport=websocket`;
	const holdMs = Number(__ENV.SOCKET_HOLD_SEC || 60) * 1000;

	const res = ws.connect(url, { tags: { name: 'socketio' } }, function (socket) {
		let joined = false;

		socket.on('open', function () {
			socketConnected.add(1);
		});

		socket.on('message', function (msg) {
			// engine.io / socket.io v4 的裸协议帧
			if (msg.startsWith('0{')) {
				// OPEN：带 auth 连接默认命名空间
				socket.send(`40${JSON.stringify({ token })}`);
			} else if (msg.startsWith('40')) {
				// CONNECT 确认：补发 user-join，进入在线用户池
				socket.send(`42${JSON.stringify(['user-join', { auth: { token } }])}`);
				joined = true;
			} else if (msg === '2') {
				// engine.io PING → PONG
				socket.send('3');
			}
		});

		// 前端每隔一段时间上报心跳，这里照做
		socket.setInterval(function () {
			if (joined) {
				socket.send(`42${JSON.stringify(['heartbeat', {}])}`);
			}
		}, 30000);

		socket.setTimeout(function () {
			socket.close();
		}, holdMs);

		socket.on('error', function (e) {
			socketFailed.add(1);
			console.error(`socket 错误：${e && e.error ? e.error() : e}`);
		});
	});

	check(res, { 'websocket 握手 101': (r) => r && r.status === 101 });
}

// ---------- 场景三：页面接口 ----------

export function browse(data) {
	const token = tokenFor(data);
	const params = { headers: authHeaders(token) };

	const responses = http.batch([
		{ method: 'GET', url: `${BASE}/api/v1/auths/`, params: { ...params, tags: { name: 'me' } } },
		{ method: 'GET', url: `${BASE}/api/models`, params: { ...params, tags: { name: 'models' } } },
		{
			method: 'GET',
			url: `${BASE}/api/v1/me/writing/home`,
			params: { ...params, tags: { name: 'writing_home' } }
		},
		{
			method: 'GET',
			url: `${BASE}/api/v1/me/classroom`,
			params: { ...params, tags: { name: 'classroom' } }
		}
	]);

	for (const r of responses) {
		check(r, { '页面接口 2xx': (x) => x.status >= 200 && x.status < 300 });
	}
}
