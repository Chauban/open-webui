import { WEBUI_API_BASE_URL } from '$lib/constants';
import type {
	EditorOperationType,
	StudentGrowthGoal,
	StudentProfile,
	StudentProfileFilters,
	TeacherStudentNote,
	TeacherStudentProfile,
	WritingSourceType,
	WritingVersionTrigger
} from './types';
import { buildProfileQuery } from '$lib/utils/growth-profile';

export type * from './types';

export const getWritingProcessSummary = async (
	token: string,
	sessionId: string
): Promise<{ clarification_answered_count: number }> => {
	return fetch(`${WEBUI_API_BASE_URL}/writing/${sessionId}/process-summary`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

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

export type CoachingStyle = 'socratic' | 'balanced' | 'hands_off';

export const createAssignment = async (
	token: string,
	payload: {
		title: string;
		description?: string;
		classroom_ids: string[];
		due_at: number;
		score_max: number;
		coaching_style: CoachingStyle;
		challenge_enabled?: boolean;
		challenge_rounds?: number;
		challenge_focus_keys?: string[];
		rubric_schema: {
			criteria: Array<{ key: string; label: string; max_score: number }>;
		};
	}
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

export const grantAssignmentExtension = async (
	token: string,
	assignmentId: string,
	studentUserId: string,
	payload: { due_at: number; reason?: string | null }
) => {
	return fetch(
		`${WEBUI_API_BASE_URL}/teacher/assignments/${assignmentId}/extensions/${studentUserId}`,
		{
			method: 'PUT',
			headers: withAuth(token),
			body: JSON.stringify(payload)
		}
	).then(handleJson);
};

export const revokeAssignmentExtension = async (
	token: string,
	assignmentId: string,
	studentUserId: string
) => {
	return fetch(
		`${WEBUI_API_BASE_URL}/teacher/assignments/${assignmentId}/extensions/${studentUserId}`,
		{
			method: 'DELETE',
			headers: withAuth(token)
		}
	).then(handleJson);
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
		score_max?: number;
		coaching_style?: CoachingStyle;
		challenge_enabled?: boolean;
		challenge_rounds?: number;
		challenge_focus_keys?: string[];
		rubric_schema?: {
			criteria: Array<{ key: string; label: string; max_score: number }>;
		};
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
		trigger_type: WritingVersionTrigger;
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
			source_type: WritingSourceType;
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
			op_type: EditorOperationType;
			source_type: WritingSourceType;
			start_offset?: number | null;
			end_offset?: number | null;
			inserted_text?: string | null;
			deleted_text?: string | null;
			batch_id: string;
			occurred_at_ms: number;
			client_sequence: number;
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
		ai_used: boolean;
		ai_help_types: string[];
		data_completeness: {
			version_data_complete: boolean;
			editor_operations_complete: boolean;
			source_tracking_complete: boolean;
		};
		reflection: {
			action: string;
			location: string;
			judgement: string;
			next_step: string;
			other_ai_help?: string | null;
		};
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
		rubric_scores?: Record<string, number> | null;
		returned_comment?: string;
		resubmit_due_at?: number | null;
		/** 让质疑读者下一轮就着这条退回意见追问。只在退回时有意义。 */
		challenge_followup?: boolean;
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
	studentUserId: string,
	filters: StudentProfileFilters = {}
): Promise<TeacherStudentProfile> => {
	const query = buildProfileQuery(filters);
	const suffix = query ? `?${query}` : '';
	return fetch(
		`${WEBUI_API_BASE_URL}/teacher/classrooms/${classroomId}/students/${studentUserId}/profile${suffix}`,
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

export const getMyWritingProfile = async (
	token: string,
	filters: StudentProfileFilters = {}
): Promise<StudentProfile> => {
	const query = buildProfileQuery(filters);
	const suffix = query ? `?${query}` : '';
	return fetch(`${WEBUI_API_BASE_URL}/me/writing/profile${suffix}`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const createGrowthGoal = async (
	token: string,
	payload: {
		goal_text: string;
		classroom_id?: string;
		assignment_id?: string;
		target_at?: number;
	}
): Promise<StudentGrowthGoal> => {
	return fetch(`${WEBUI_API_BASE_URL}/me/writing/goals`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const updateGrowthGoal = async (
	token: string,
	goalId: string,
	payload: {
		goal_text?: string;
		target_at?: number | null;
		status?: 'active' | 'completed' | 'archived';
	}
): Promise<StudentGrowthGoal> => {
	return fetch(`${WEBUI_API_BASE_URL}/me/writing/goals/${goalId}`, {
		method: 'PATCH',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const createTeacherStudentNote = async (
	token: string,
	classroomId: string,
	studentUserId: string,
	payload: { content: string; observed_at?: number }
): Promise<TeacherStudentNote> => {
	return fetch(
		`${WEBUI_API_BASE_URL}/teacher/classrooms/${classroomId}/students/${studentUserId}/profile-notes`,
		{
			method: 'POST',
			headers: withAuth(token),
			body: JSON.stringify(payload)
		}
	).then(handleJson);
};

export const updateTeacherStudentNote = async (
	token: string,
	noteId: string,
	payload: { content?: string; observed_at?: number }
): Promise<TeacherStudentNote> => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/profile-notes/${noteId}`, {
		method: 'PATCH',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const deleteTeacherStudentNote = async (token: string, noteId: string) => {
	return fetch(`${WEBUI_API_BASE_URL}/teacher/profile-notes/${noteId}`, {
		method: 'DELETE',
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

// --- 提交前质疑环节 -------------------------------------------------------
// 质疑读者与左侧辅导助手是两个相反的角色：辅导助手负责帮，质疑读者只负责问，
// 且它的输出进不了正文。所以这套接口独立于聊天，不复用 chat 的任何通道。

export type ChallengeStatus = 'in_progress' | 'completed' | 'skipped';

export type ChallengeTurn = {
	id: string;
	challenge_session_id: string;
	turn_no: number;
	focus_key: string;
	challenge_text: string;
	/** 这一轮质疑引用的原文片段，是修订判定与正文定位的锚点。 */
	quoted_span: string;
	response_text: string | null;
	responded_at: number | null;
	created_at: number;
};

/**
 * 一条仍不成立的点。
 *
 * focus_key 由服务端按轮次映射得出，是班级层面按维度聚合的依据。归属不上时为 null，
 * 那种条目照样展示给学生，只是不进统计表。
 */
export type ChallengeClosingItem = {
	text: string;
	turn_no: number | null;
	focus_key: string | null;
};

export type ChallengeClosing = {
	stood: string[];
	unresolved: ChallengeClosingItem[];
};

export type ChallengeSession = {
	id: string;
	writing_session_id: string;
	assignment_id: string;
	student_id: string;
	submission_round_no: number;
	/** 契约页未开始就跳过时为空：那种情况下不存在「被质疑的那一稿」。 */
	source_version_id: string | null;
	focus_keys: string[];
	planned_rounds: number;
	status: ChallengeStatus;
	closing_summary_json: ChallengeClosing | null;
	checklist_state_json: { checked_indexes: number[] } | null;
	started_at: number;
	ended_at: number | null;
};

/** 一轮质疑对应的那处正文，在最终交上来的稿子里变了没有。 */
export type ChallengeRevisionTurn = {
	turn_no: number;
	focus_key: string;
	quoted_span: string;
	changed: boolean;
	/** 这句在最终稿里的样子；被整段删掉时为 null。 */
	final_span: string | null;
};

export type ChallengeRevision = {
	revised: boolean;
	changed_spans: number;
	total_spans: number;
	turns: ChallengeRevisionTurn[];
};

export type ChallengeDetail = {
	session: ChallengeSession;
	turns: ChallengeTurn[];
	/** 只有教师读提交时才带，提交那一刻就冻好了。 */
	revision?: ChallengeRevision | null;
};

export const startAssignmentChallenge = async (
	token: string,
	assignmentId: string,
	payload: { writing_session_id: string; model: string }
): Promise<ChallengeDetail> => {
	return fetch(`${WEBUI_API_BASE_URL}/assignments/${assignmentId}/challenge/start`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const getCurrentAssignmentChallenge = async (
	token: string,
	assignmentId: string,
	writingSessionId: string
): Promise<ChallengeDetail | null> => {
	const query = new URLSearchParams({ writing_session_id: writingSessionId });
	return fetch(`${WEBUI_API_BASE_URL}/assignments/${assignmentId}/challenge/current?${query}`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

export const respondToChallenge = async (
	token: string,
	challengeSessionId: string,
	payload: { turn_no: number; response_text: string; model: string }
): Promise<ChallengeDetail> => {
	return fetch(`${WEBUI_API_BASE_URL}/challenge/${challengeSessionId}/respond`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify(payload)
	}).then(handleJson);
};

export const skipAssignmentChallenge = async (
	token: string,
	challengeSessionId: string
): Promise<ChallengeDetail> => {
	return fetch(`${WEBUI_API_BASE_URL}/challenge/${challengeSessionId}/skip`, {
		method: 'POST',
		headers: withAuth(token)
	}).then(handleJson);
};

/**
 * 契约页尚未开始就跳过。
 *
 * 没有 session 可标记，所以按作业 + 写作会话落一条 skipped。不落的话，连开都不开
 * 的那批学生在质疑维度上完全空白，而那恰恰是最该被教师看到的信号。
 */
export const skipAssignmentChallengeBeforeStart = async (
	token: string,
	assignmentId: string,
	writingSessionId: string
): Promise<ChallengeDetail> => {
	return fetch(`${WEBUI_API_BASE_URL}/assignments/${assignmentId}/challenge/skip`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify({ writing_session_id: writingSessionId })
	}).then(handleJson);
};

export const updateChallengeChecklist = async (
	token: string,
	challengeSessionId: string,
	checkedIndexes: number[]
): Promise<ChallengeDetail> => {
	return fetch(`${WEBUI_API_BASE_URL}/challenge/${challengeSessionId}/checklist`, {
		method: 'PATCH',
		headers: withAuth(token),
		body: JSON.stringify({ checked_indexes: checkedIndexes })
	}).then(handleJson);
};

/** 一处预设漏洞有没有被找出来。只报命中，不给分、不给等级。 */
export type CritiqueMatch = {
	key: string;
	focus_key: string;
	hit: boolean;
};

export type CritiqueAttempt = {
	id: string;
	assignment_id: string;
	student_id: string;
	items_json: string[];
	matches_json: CritiqueMatch[];
	completed_at: number;
};

export type CritiqueState = {
	enabled: boolean;
	text: string;
	completed: boolean;
	attempt: CritiqueAttempt | null;
};

export const getAssignmentCritique = async (
	token: string,
	assignmentId: string
): Promise<CritiqueState> => {
	return fetch(`${WEBUI_API_BASE_URL}/assignments/${assignmentId}/critique`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};

/** 不设及格线：找出一条也放行，命中数只记录。 */
export const submitAssignmentCritique = async (
	token: string,
	assignmentId: string,
	items: string[],
	model: string
): Promise<CritiqueState> => {
	return fetch(`${WEBUI_API_BASE_URL}/assignments/${assignmentId}/critique`, {
		method: 'POST',
		headers: withAuth(token),
		body: JSON.stringify({ items, model })
	}).then(handleJson);
};

/** 一类「本班普遍站不住的论证」。只报频次，不对班级下评价性结论。 */
export type ChallengeInsightCategory = {
	name: string;
	hits: number;
	samples: string[];
	advice: string;
};

export type ChallengeInsight = {
	categories: ChallengeInsightCategory[];
	sample_size: number;
	below_threshold: boolean;
	threshold: number;
	generated_at: number | null;
};

/**
 * 生成班级教研分析。
 *
 * 由教师主动触发，不随看板自动加载——这是唯一一处会调模型的班级分析。服务端按输入
 * 哈希缓存，内容没变不会重算。
 */
export const generateChallengeInsight = async (
	token: string,
	assignmentId: string,
	model: string
): Promise<ChallengeInsight> => {
	return fetch(
		`${WEBUI_API_BASE_URL}/teacher/assignments/${assignmentId}/challenge-insight`,
		{
			method: 'POST',
			headers: withAuth(token),
			body: JSON.stringify({ model })
		}
	).then(handleJson);
};

export const getSubmissionChallenge = async (
	token: string,
	submissionId: string
): Promise<ChallengeDetail | null> => {
	return fetch(`${WEBUI_API_BASE_URL}/submissions/${submissionId}/challenge`, {
		method: 'GET',
		headers: withAuth(token)
	}).then(handleJson);
};
