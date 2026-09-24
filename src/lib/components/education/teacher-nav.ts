// 教师端的两级导航:顶栏常驻四个分区,作业/班级这两个对象再各有一条子标签。
// 此前分区导航放在正文里(一滚动就看不见),对象的子页之间靠按钮互跳,
// 按钮名每页不一样(「作业」「看板」「返回」),这里收成一份定义。

export type TeacherNavLink = { label: string; href: string };

export const TEACHER_SECTIONS: TeacherNavLink[] = [
	{ label: 'Overview', href: '/teacher' },
	{ label: 'Classrooms', href: '/teacher/classrooms' },
	{ label: 'Assignments', href: '/teacher/assignments' },
	{ label: 'Review', href: '/teacher/review' }
];

// 批改工作台挂在 /teacher/submissions/ 下,归属「批改」分区。
export const isTeacherSectionActive = (href: string, pathname: string) => {
	if (href === '/teacher') return pathname === '/teacher';
	if (href === '/teacher/review' && pathname.startsWith('/teacher/submissions/')) return true;
	return pathname === href || pathname.startsWith(`${href}/`);
};

export const assignmentTabs = (assignmentId: string): TeacherNavLink[] => [
	{ label: 'Overview', href: `/teacher/assignments/${assignmentId}` },
	{ label: 'Submissions', href: `/teacher/assignments/${assignmentId}/submissions` },
	{ label: 'Assignment Analysis', href: `/teacher/assignments/${assignmentId}/dashboard` },
	{ label: 'Settings', href: `/teacher/assignments/${assignmentId}/settings` }
];

export const classroomTabs = (classroomId: string): TeacherNavLink[] => [
	{ label: 'Overview', href: `/teacher/classrooms/${classroomId}` },
	{ label: 'Students', href: `/teacher/classrooms/${classroomId}/students` }
];
