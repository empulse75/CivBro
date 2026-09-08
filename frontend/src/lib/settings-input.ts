export function isApiKeyDeleteCommand(value: string): boolean {
  return value.trim().toLowerCase() === "delete";
}
