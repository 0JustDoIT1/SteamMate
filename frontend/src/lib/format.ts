/** Steam 가격은 최소 단위×100으로 온다(예: KRW 1100000 = ₩11,000). */
export function formatPrice(amount: number | null | undefined, currency: string | null | undefined) {
  if (amount == null || !currency) return null;
  if (amount === 0) return "무료";
  try {
    return new Intl.NumberFormat("ko-KR", { style: "currency", currency }).format(amount / 100);
  } catch {
    return `${(amount / 100).toLocaleString("ko-KR")} ${currency}`;
  }
}

export function formatCount(n: number | null | undefined) {
  if (n == null) return null;
  return new Intl.NumberFormat("ko-KR", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });
}

export function steamStoreUrl(appid: number) {
  return `https://store.steampowered.com/app/${appid}/`;
}
