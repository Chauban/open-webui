type NavigationUser = { education_role?: string | null } | null | undefined;

export const getHomeHref = (user: NavigationUser) =>
	user?.education_role === 'student' ? '/me/writing' : '/';

export const getSignInRedirect = (user: NavigationUser, redirect?: string | null) =>
	redirect && redirect !== '/' ? redirect : getHomeHref(user);
