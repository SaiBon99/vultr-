export const shortHash = (h: string): string =>
  `${h.slice(0, 14)}...${h.slice(-6)}`;

export function formatTime(iso: string): string {
  return (
    new Intl.DateTimeFormat("en-GB", {
      dateStyle: "medium",
      timeStyle: "medium",
      timeZone: "UTC",
    }).format(new Date(iso)) + " UTC"
  );
}
