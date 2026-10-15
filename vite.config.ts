import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { svelteTesting } from '@testing-library/svelte/vite';

import { viteStaticCopy } from 'vite-plugin-static-copy';

const backendTarget = process.env.WEBUI_BACKEND_URL || 'http://localhost:8080';

export default defineConfig({
	plugins: [
		sveltekit(),
		svelteTesting(),
		viteStaticCopy({
			targets: [
				{
					src: 'node_modules/onnxruntime-web/dist/*.jsep.*',

					dest: 'wasm'
				},
				// 作业写作区在浏览器里读 PDF 时按需取用(src/lib/utils/pdf-import.ts):
				// 中日韩字符映射与标准字体,不进 JS 包,只在 PDF 用到时下载对应的那一个文件。
				{
					src: 'node_modules/pdfjs-dist/cmaps/*',
					dest: 'pdfjs/cmaps'
				},
				{
					src: 'node_modules/pdfjs-dist/standard_fonts/*',
					dest: 'pdfjs/standard_fonts'
				}
			]
		})
	],
	define: {
		APP_VERSION: JSON.stringify(process.env.npm_package_version),
		APP_BUILD_HASH: JSON.stringify(process.env.APP_BUILD_HASH || 'dev-build')
	},
	build: {
		sourcemap: true
	},
	server: {
		proxy: {
			'/api': {
				target: backendTarget,
				changeOrigin: true,
				ws: true
			},
			'/ollama': {
				target: backendTarget,
				changeOrigin: true
			},
			'/openai': {
				target: backendTarget,
				changeOrigin: true
			},
			'/oauth': {
				target: backendTarget,
				changeOrigin: true
			},
			'/ws': {
				target: backendTarget,
				changeOrigin: true,
				ws: true
			},
			'/static': {
				target: backendTarget,
				changeOrigin: true
			},
			'/audio': {
				target: backendTarget,
				changeOrigin: true
			},
			'/opensearch.xml': {
				target: backendTarget,
				changeOrigin: true
			}
		},
		watch: {
			ignored: ['**/.tmp/**']
		}
	},
	test: {
		exclude: [
			'**/node_modules/**',
			'**/.git/**',
			'**/.tmp/**',
			'**/.pytest_cache/**',
			'**/.tmppytest-cache/**',
			'**/*pytest-cache/**',
			'pytest-cache-files*/**'
		]
	},
	worker: {
		format: 'es'
	},
	esbuild: {
		pure: process.env.ENV === 'dev' ? [] : ['console.log', 'console.debug', 'console.error']
	}
});
