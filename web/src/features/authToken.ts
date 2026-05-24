export function readOATokenCookie(cookieSource = typeof document !== "undefined" ? document.cookie : ""): string | null {
  const target = "Admin-Token=";
  const parts = cookieSource.split(";").map((item) => item.trim());
  for (const part of parts) {
    if (part.startsWith(target)) {
      const token = decodeURIComponent(part.slice(target.length)).trim();
      return token.length > 0 ? token : null;
    }
  }
  return null;
}
