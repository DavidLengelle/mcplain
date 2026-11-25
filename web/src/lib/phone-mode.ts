export const PHONE_QUERY = "(max-width: 767.98px), (max-height: 499.98px)";

export const DESK_QUERY = "(min-width: 768px) and (min-height: 500px)";

export function isPhoneMode(): boolean {
  return window.matchMedia(PHONE_QUERY).matches;
}
