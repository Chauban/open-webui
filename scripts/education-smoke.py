import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / 'backend'
if str(BACKEND_ROOT) not in sys.path:
	sys.path.insert(0, str(BACKEND_ROOT))

import open_webui.internal.db as internal_db  # noqa: E402
from open_webui.internal.db import get_session  # noqa: E402
from open_webui.models.access_grants import AccessGrant  # noqa: E402
from open_webui.models.chats import Chat  # noqa: E402
from open_webui.models.chat_messages import ChatMessage  # noqa: E402
from open_webui.models.education import (  # noqa: E402
	Assignment,
	Classroom,
	ClassroomMember,
	MicroReflection,
	ProvenanceSegment,
	Submission,
	WritingSession,
	WritingVersion,
)
from open_webui.models.notes import Note  # noqa: E402
from open_webui.models.users import User, Users  # noqa: E402
from open_webui.routers.education import router as education_router  # noqa: E402
from open_webui.utils.auth import get_verified_user  # noqa: E402

internal_db.DATABASE_ENABLE_SESSION_SHARING = True


class UserContext:
	current_user = None


def create_app(session_factory):
	app = FastAPI()
	app.include_router(education_router, prefix='/api/v1')

	def override_session():
		db = session_factory()
		try:
			yield db
		finally:
			db.close()

	def override_verified_user():
		if UserContext.current_user is None:
			raise HTTPException(status_code=401, detail='Missing test user')
		return UserContext.current_user

	app.dependency_overrides[get_session] = override_session
	app.dependency_overrides[get_verified_user] = override_verified_user
	return app


def seed_user(session, user_id: str, name: str, email: str, education_role: str):
	Users.insert_new_user(
		id=user_id,
		name=name,
		email=email,
		role='user',
		profile_image_url='/user.png',
		db=session
	)
	db_user = Users.get_user_by_id(user_id, db=session)
	Users.update_user_by_id(
		user_id,
		{
			'info': {
				**(db_user.info or {}),
				'education_role': education_role,
			}
		},
		db=session
	)
	return Users.get_user_by_id(user_id, db=session)


def set_user(user_model):
	UserContext.current_user = user_model


def main():
	with tempfile.TemporaryDirectory() as tmpdir:
		db_path = Path(tmpdir) / 'education_smoke.db'
		engine = create_engine(
			f'sqlite:///{db_path}',
			connect_args={'check_same_thread': False}
		)
		SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
		for table in [
			User.__table__,
			AccessGrant.__table__,
			Note.__table__,
			Chat.__table__,
			ChatMessage.__table__,
			Classroom.__table__,
			ClassroomMember.__table__,
			Assignment.__table__,
			WritingSession.__table__,
			WritingVersion.__table__,
			ProvenanceSegment.__table__,
			MicroReflection.__table__,
			Submission.__table__,
		]:
			table.create(bind=engine, checkfirst=True)
		with engine.begin() as connection:
			connection.exec_driver_sql('DROP INDEX IF EXISTS classroom_member_user_idx')

		with SessionLocal() as session:
			teacher = seed_user(session, 'teacher-1', 'Teacher One', 'teacher@example.com', 'teacher')
			student = seed_user(session, 'student-1', 'Student One', 'student@example.com', 'student')
			other_student = seed_user(
				session, 'student-2', 'Student Two', 'student2@example.com', 'student'
			)

		client = TestClient(create_app(SessionLocal))

		set_user(teacher)
		empty_classroom_res = client.post('/api/v1/classrooms', json={'name': '   '})
		assert empty_classroom_res.status_code == 400, empty_classroom_res.text

		create_classroom_res = client.post('/api/v1/classrooms', json={'name': 'Grade 8 Writing'})
		assert create_classroom_res.status_code == 200, create_classroom_res.text
		classroom = create_classroom_res.json()['classroom']
		assert classroom['name'] == 'Grade 8 Writing'

		create_assignment_res = client.post(
			'/api/v1/assignments',
			json={
				'title': 'Argument Essay 1',
				'description': 'Write a short argument essay.',
				'classroom_id': classroom['id']
			}
		)
		assert create_assignment_res.status_code == 200, create_assignment_res.text
		assignment = create_assignment_res.json()

		set_user(student)
		blank_join_res = client.post('/api/v1/classrooms/join', json={'invite_code': '   '})
		assert blank_join_res.status_code == 400, blank_join_res.text

		join_res = client.post(
			'/api/v1/classrooms/join',
			json={'invite_code': classroom['invite_code']}
		)
		assert join_res.status_code == 200, join_res.text

		student_classroom_res = client.get('/api/v1/me/classroom')
		assert student_classroom_res.status_code == 200, student_classroom_res.text
		assert student_classroom_res.json()['classroom']['id'] == classroom['id']

		workspace_res = client.get(f"/api/v1/assignments/{assignment['id']}/workspace")
		assert workspace_res.status_code == 200, workspace_res.text
		workspace = workspace_res.json()
		assert workspace['writing_session']['student_id'] == student.id
		assert workspace['assignment']['id'] == assignment['id']

		session_id = workspace['writing_session']['id']
		autosave_res = client.post(
			f'/api/v1/writing-sessions/{session_id}/autosave',
			json={
				'content_json': {'type': 'doc', 'content': []},
				'content_html': '<p>Draft update</p>',
				'content_text': 'Draft update'
			}
		)
		assert autosave_res.status_code == 200, autosave_res.text

		version_res = client.post(
			f'/api/v1/writing-sessions/{session_id}/versions',
			json={
				'trigger_type': 'manual',
				'content_json': {'type': 'doc', 'content': []},
				'content_text': 'Draft update'
			}
		)
		assert version_res.status_code == 200, version_res.text
		version = version_res.json()

		provenance_res = client.post(
			f'/api/v1/writing-sessions/{session_id}/provenance',
			json={
				'version_id': version['id'],
				'segments': [
					{
						'segment_id': 'seg-1',
						'source_type': 'user_typed',
						'segment_text': 'Draft update'
					}
				]
			}
		)
		assert provenance_res.status_code == 200, provenance_res.text

		chat_res = client.post(
			f'/api/v1/writing-sessions/{session_id}/chat/messages/msg-1',
			json={
				'message': {
					'id': 'msg-1',
					'role': 'user',
					'content': 'Help me outline this essay.'
				}
			}
		)
		assert chat_res.status_code == 200, chat_res.text

		set_user(teacher)
		teacher_classroom_res = client.get('/api/v1/me/classroom')
		assert teacher_classroom_res.status_code == 200, teacher_classroom_res.text
		assert teacher_classroom_res.json()['classroom']['id'] == classroom['id']

		teacher_workspace_res = client.get(f"/api/v1/assignments/{assignment['id']}/workspace")
		assert teacher_workspace_res.status_code == 403, teacher_workspace_res.text

		second_classroom_res = client.post('/api/v1/classrooms', json={'name': 'Grade 9 Writing'})
		assert second_classroom_res.status_code == 200, second_classroom_res.text
		second_classroom = second_classroom_res.json()['classroom']

		regenerated_res = client.post(f"/api/v1/classrooms/{classroom['id']}/invite-code/regenerate")
		assert regenerated_res.status_code == 200, regenerated_res.text
		regenerated_classroom = regenerated_res.json()['classroom']
		assert regenerated_classroom['invite_code'] != classroom['invite_code']

		set_user(student)
		old_join_res = client.post('/api/v1/classrooms/join', json={'invite_code': classroom['invite_code']})
		assert old_join_res.status_code == 400, old_join_res.text

		rejoin_res = client.post(
			'/api/v1/classrooms/join',
			json={'invite_code': second_classroom['invite_code']}
		)
		assert rejoin_res.status_code == 400, rejoin_res.text

		set_user(other_student)
		forbidden_autosave_res = client.post(
			f'/api/v1/writing-sessions/{session_id}/autosave',
			json={
				'content_json': None,
				'content_html': '<p>Blocked</p>',
				'content_text': 'Blocked'
			}
		)
		assert forbidden_autosave_res.status_code == 403, forbidden_autosave_res.text

		foreign_workspace_res = client.get(f"/api/v1/assignments/{assignment['id']}/workspace")
		assert foreign_workspace_res.status_code == 403, foreign_workspace_res.text

		engine.dispose()
	print('education-smoke-ok')


if __name__ == '__main__':
	main()
