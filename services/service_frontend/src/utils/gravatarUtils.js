import MD5 from 'crypto-js/md5';

export function getGravatarUrl(email, size = 64) {
  if (!email || !email.trim()) return null;
  const hash = MD5(email.toLowerCase().trim()).toString();
  return `https://www.gravatar.com/avatar/${hash}?s=${size}&d=mp`;
}
