export type WritingSaveProblem = {
	message: string;
	retryable: boolean;
	login: boolean;
	requestId?: string;
	field?: string;
	retryAfterMs?: number;
};

export function writingSaveProblem(error: any): WritingSaveProblem {
	const status = Number(error?.status ?? 0);
	const detail = typeof error?.detail === 'string' ? error.detail : '';
	let message = '保存未完成，请重试；如仍失败，请将错误编号反馈给老师。';
	if (status === 401) message = '登录已过期，请先保留稿件，再重新登录。';
	else if (detail.includes('already been reviewed'))
		message = '作业已批改，当前修改无法保存，请联系老师。';
	else if (detail === 'Assignment is hidden') message = '老师已隐藏这份作业，请联系老师确认。';
	else if (status === 403) message = '当前账号没有保存权限，请联系老师确认账号和作业。';
	else if (status === 404 || /material|note reference|placeholder|text layer/i.test(detail))
		message = '稿件中的图片或注释无法关联到本作业，请保留稿件后重新上传原文件。';
	else if (status === 413 || /too (much text|complex|many)/i.test(detail))
		message = '稿件内容或附件超过保存限制，请先下载备份，再减少内容或附件。';
	else if (status === 409) message = '稿件状态已变化，请先保留当前稿件，再重新打开作业核对。';
	else if (status === 400 || status === 422)
		message = '稿件格式未通过检查，请先下载备份，再检查最近粘贴的格式或重新导入原文件。';
	else if (status === 429) message = '保存请求较多，请稍后重试。';
	else if (status >= 500) message = '服务器暂时无法保存，请稍后重试。';
	else if (
		error instanceof TypeError ||
		error?.name === 'AbortError' ||
		error?.name === 'TimeoutError'
	)
		message = '网络连接中断或保存超时，请检查网络后重试。';
	return {
		message,
		retryable:
			status === 408 ||
			status === 429 ||
			status >= 500 ||
			error instanceof TypeError ||
			['AbortError', 'TimeoutError'].includes(error?.name),
		login: status === 401,
		requestId: error?.requestId,
		field: error?.field,
		retryAfterMs: error?.retryAfterMs
	};
}

/** Clear the timer when the save wins; a timeout never permits sending an old draft. */
export async function waitForWritingSave(save: Promise<void>, timeoutMs = 5000): Promise<boolean> {
	let timer: ReturnType<typeof setTimeout>;
	try {
		return await Promise.race([
			save.then(() => true),
			new Promise<boolean>((resolve) => {
				timer = setTimeout(() => resolve(false), timeoutMs);
			})
		]);
	} finally {
		clearTimeout(timer!);
	}
}
