import { WEBUI_API_BASE_URL } from '$lib/constants';

const parseErrorResponse = async (res: Response) => {
	const contentType = res.headers.get('content-type') || '';
	if (contentType.includes('application/json')) {
		try {
			return await res.json();
		} catch {}
	}

	const text = await res.text();
	return {
		detail: text || res.statusText || 'Request failed',
		status: res.status
	};
};

const handleJson = async (res: Response) => {
	if (!res.ok) {
		throw await parseErrorResponse(res);
	}
	return res.json();
};

const withAuth = (token: string) => ({
	Accept: 'application/json',
	'Content-Type': 'application/json',
	authorization: `Bearer ${token}`
});

export const getMyClassroom = async (token: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/me/classroom`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const createClassroom = async (
	token: string,
	payload: {
		name: string;
	}
) => {
	return fetch(`${WEBUI_API_BASE_URL}/classrooms`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const joinClassroom = async (
	token: string,
	payload: {
		invite_code: string;
	}
) => {
	return fetch(`${WEBUI_API_BASE_URL}/classrooms/join`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const regenerateClassroomInviteCode = async (token: string, classroomId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/classrooms/${classroomId}/invite-code/regenerate`, {
		method: 'POST',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getTeacherClassrooms = async (token: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/classrooms`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getTeacherOverview = async (token: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/overview`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getTeacherAssignments = async (token: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/assignments`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getTeacherReview = async (
	token: string,
	params: {
		review_status?: string;
		classroom_id?: string;
		assignment_id?: string;
		sort?: string;
		limit?: number;
		offset?: number;
	} = {}
) => {
	const query = new URLSearchParams();
	for (const [key, value] of Object.entries(params)) {
		if (value !== undefined && value !== null && `${value}` !== '') {
			query.set(key, `${value}`);
		}
	}
	const suffix = query.toString() ? `?${query.toString()}` : '';
	return fetch(`${WEBUI_API_BASE_URL}/teacher/review${suffix}`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getTeacherClassroom = async (token: string, classroomId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/classrooms/${classroomId}`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getClassroomMembers = async (token: string, classroomId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/classrooms/${classroomId}/members`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const addClassroomMember = async (
	token: string,
	classroomId: string,
	payload: { user_id: string; member_role?: string }
) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/classrooms/${classroomId}/members`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const removeClassroomMember = async (
	token: string,
	classroomId: string,
	memberUserId: string
) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/classrooms/${classroomId}/members/${memberUserId}`, {
		method: 'DELETE',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getTeacherClassroomAssignments = async (token: string, classroomId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/classrooms/${classroomId}/assignments`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const createAssignment = async (
	token: string,
	payload: { title: string; description?: string; classroom_ids: string[]; due_at: number }
) => {
	return fetch(`${WEBUI_API_BASE_URL}/assignments`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const getTeacherAssignment = async (token: string, assignmentId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/assignments/${assignmentId}`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const deleteAssignment = async (token: string, assignmentId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/assignments/${assignmentId}`, {
		method: 'DELETE',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getAssignmentUnsubmittedStudents = async (token: string, assignmentId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/assignments/${assignmentId}/unsubmitted`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const remindUnsubmittedStudents = async (
	token: string,
	assignmentId: string,
	payload: { user_ids?: string[] } = {}
) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/assignments/${assignmentId}/remind`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const updateAssignment = async (
	token: string,
	assignmentId: string,
	payload: {
		title?: string;
		description?: string;
		classroom_id?: string;
		status?: string;
		due_at?: number;
	}
) => {
	return fetch(`${WEBUI_API_BASE_URL}/assignments/${assignmentId}`, {
		method: 'PATCH',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const archiveAssignment = async (token: string, assignmentId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/assignments/${assignmentId}/archive`, {
		method: 'POST',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getAssignmentWorkspace = async (token: string, assignmentId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/assignments/${assignmentId}/workspace`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getWritingHome = async (token: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/me/writing/home`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const createPersonalWriting = async (
	token: string,
	payload: {
		title?: string;
	}
) => {
	return fetch(`${WEBUI_API_BASE_URL}/me/writing/personal`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const getWritingWorkspace = async (token: string, sessionId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/writing/${sessionId}/workspace`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const deletePersonalWriting = async (token: string, sessionId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/me/writing/personal/${sessionId}`, {
		method: 'DELETE',
		headers: withAuth(token)
	}).then(handleJson);
};

export const autosaveWritingSession = async (
	token: string,
	sessionId: string,
	payload: {
		content_json: object | null;
		content_html?: string;
		content_text: string;
		save_reason?: string;
	}
) => {
	return fetch(`${WEBUI_API_BASE_URL}/writing-sessions/${sessionId}/autosave`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const createWritingVersion = async (
	token: string,
	sessionId: string,
	payload: {
		trigger_type: string;
		content_json: object | null;
		content_text: string;
	}
) => {
	return fetch(`${WEBUI_API_BASE_URL}/writing-sessions/${sessionId}/versions`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const createProvenanceSegments = async (
	token: string,
	sessionId: string,
	payload: {
		version_id?: string | null;
		segments: Array<{
			segment_id: string;
			source_type: string;
			segment_text: string;
			source_message_id?: string | null;
			start_offset?: number | null;
			end_offset?: number | null;
			metadata_json?: Record<string, unknown> | null;
		}>;
		replace_existing?: boolean;
	}
) => {
	return fetch(`${WEBUI_API_BASE_URL}/writing-sessions/${sessionId}/provenance`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const createEditorOperations = async (
	token: string,
	sessionId: string,
	payload: {
		operations: Array<{
			op_type: string;
			source_type: string;
			start_offset?: number | null;
			end_offset?: number | null;
			inserted_text?: string | null;
			deleted_text?: string | null;
			batch_id: string;
			metadata_json?: Record<string, unknown> | null;
		}>;
	}
) => {
	return fetch(`${WEBUI_API_BASE_URL}/writing-sessions/${sessionId}/operations`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const setWritingSessionActiveChat = async (
	token: string,
	sessionId: string,
	chatId: string | null
) => {
	return fetch(`${WEBUI_API_BASE_URL}/writing-sessions/${sessionId}/active-chat`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify({
			chat_id: chatId
		})
	}).then(handleJson);
};

export const upsertWritingChatMessage = async (
	token: string,
	sessionId: string,
	messageId: string,
	payload: {
		message: Record<string, unknown>;
	}
) => {
	return fetch(`${WEBUI_API_BASE_URL}/writing-sessions/${sessionId}/chat/messages/${messageId}`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const submitAssignment = async (
	token: string,
	assignmentId: string,
	payload: {
		writing_session_id: string;
		final_content_json: object | null;
		final_content_html?: string;
		final_content_text: string;
		ai_help_types: string[];
		reflection_text: string;
	}
) => {
	return fetch(`${WEBUI_API_BASE_URL}/assignments/${assignmentId}/submit`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const getMyAssignmentSubmissions = async (token: string, assignmentId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/assignments/${assignmentId}/me/submissions`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getTeacherSubmissions = async (token: string, assignmentId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/assignments/${assignmentId}/submissions`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getSubmissionReview = async (token: string, submissionId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/submissions/${submissionId}/review`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const saveSubmissionReview = async (
	token: string,
	submissionId: string,
	payload: {
		review_status: string;
		score?: number | null;
		overall_comment?: string;
		rubric_json?: Record<string, unknown> | null;
		returned_comment?: string;
		resubmit_due_at?: number | null;
	}
) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/submissions/${submissionId}/review`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const getSubmissionVersions = async (token: string, submissionId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/submissions/${submissionId}/versions`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const recomputeSubmissionAnalysis = async (token: string, submissionId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/submissions/${submissionId}/analysis`, {
		method: 'POST',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getSubmissionRoundDiff = async (token: string, submissionId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/submissions/${submissionId}/diff`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getTeacherSubmissionDetail = async (token: string, submissionId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/submissions/${submissionId}`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getTeacherDashboard = async (token: string, assignmentId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/assignments/${assignmentId}/dashboard`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getSubmissionAnalysisSegmentDetail = async (
	token: string,
	submissionId: string,
	segmentId: string
) => {
	return fetch(
		`${WEBUI_API_BASE_URL}/teacher/submissions/${submissionId}/analysis/segments/${segmentId}`,
		{
			method: 'GET',
			headers: withAuth(token)
		}
	).then(handleJson);
};

export const getClassroomProgress = async (token: string, classroomId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/classrooms/${classroomId}/progress`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const bulkImportClassroomMembers = async (
	token: string,
	classroomId: string,
	payload: {
		user_ids?: string[];
		emails?: string[];
	}
) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/classrooms/${classroomId}/bulk-import`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const getStudentProfile = async (
	token: string,
	classroomId: string,
	studentUserId: string
) => {
	return fetch(
		`${WEBUI_API_BASE_URL}/teacher/classrooms/${classroomId}/students/${studentUserId}/profile`,
		{
			method: 'GET',
			headers: withAuth(token)
		}
	).then(handleJson);
};

export const bulkRemoveClassroomMembers = async (
	token: string,
	classroomId: string,
	payload: { user_ids: string[] }
) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/classrooms/${classroomId}/members/bulk-remove`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const transferClassroomMembers = async (
	token: string,
	classroomId: string,
	payload: { user_ids: string[]; target_classroom_id: string }
) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/classrooms/${classroomId}/members/transfer`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const exportClassroomProgress = async (token: string, classroomId: string) => {
	const res = await fetch(`${WEBUI_API_BASE_URL}/teacher/classrooms/${classroomId}/export`, {
		method: 'GET',
		headers: {
			Accept: 'text/csv',
			authorization: `Bearer ${token}`
		}
	});
	if (!res.ok) {
		throw await parseErrorResponse(res);
	}
	return res.text();
};

export const getMyWritingProfile = async (token: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/me/writing/profile`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getStudentAssignments = async (token: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/me/writing/assignments`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getStudentAssignmentWorkspaces = async (token: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/me/writing/workspaces`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getEducationNotificationSummary = async (token: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/me/notifications/summary`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const markEducationNotificationsRead = async (
	token: string,
	payload: {
		types?: string[];
		assignment_id?: string;
	}
) => {
	return fetch(`${WEBUI_API_BASE_URL}/me/notifications/mark-read`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};
