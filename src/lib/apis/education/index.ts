import { WEBUI_API_BASE_URL } from '$lib/constants';

const handleJson = async (res: Response) => {
	if (!res.ok) {
		throw await res.json();
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

export const createAssignment = async (
	token: string,
	payload: { title: string; description?: string; classroom_id?: string }
) => {
	return fetch(`${WEBUI_API_BASE_URL}/assignments`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const getTeacherAssignments = async (token: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/assignments`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getAssignmentMembers = async (token: string, assignmentId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/assignments/${assignmentId}/members`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const addAssignmentMember = async (
	token: string,
	assignmentId: string,
	payload: { user_id: string; member_role?: string }
) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/assignments/${assignmentId}/members`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const removeAssignmentMember = async (
	token: string,
	assignmentId: string,
	memberUserId: string
) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/assignments/${assignmentId}/members/${memberUserId}`, {
		method: 'DELETE',
		headers: withAuth(token)
	}).then(handleJson);
};

export const getAssignmentWorkspace = async (token: string, assignmentId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/assignments/${assignmentId}/workspace`, {
		method: 'GET',
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
	}
) => {
	return fetch(`${WEBUI_API_BASE_URL}/writing-sessions/${sessionId}/provenance`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
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
		ai_help_type: string;
		reflection_text: string;
	}
) => {
	return fetch(`${WEBUI_API_BASE_URL}/assignments/${assignmentId}/submit`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const getTeacherSubmissions = async (token: string, assignmentId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/assignments/${assignmentId}/submissions`, {
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

export const getStudentDashboard = async (token: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/me/writing/dashboard`, {
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
