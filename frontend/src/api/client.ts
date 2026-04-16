// 이 파일은 fetch 공통 래퍼를 정의한다.
export async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const { headers, ...rest } = options ?? {};
  const response = await fetch(url, {
    cache: 'no-store',
    ...rest,
    headers: {
      'Cache-Control': 'no-cache',
      Pragma: 'no-cache',
      ...(headers ?? {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${text}`);
  }

  return (await response.json()) as T;
}
