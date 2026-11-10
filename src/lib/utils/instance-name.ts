/** Keep the instance visible when several RightWrite sites are open together. */
export const getInstanceName = (name: string, hostname: string): string => {
	const host = hostname.toLowerCase().replace(/\.$/, '');
	let instance = '';
	if (host === 'localhost' || host === '[::1]' || host === '::1' || /^127\./.test(host)) {
		instance = '本地';
	} else if (host === 'hitsz.rightwrite.cc') {
		instance = 'HIT';
	} else if (host === 'rightwrite.cc' || host === 'www.rightwrite.cc') {
		return 'Rightwrite';
	}
	return instance ? `${instance} · ${name}` : name;
};
