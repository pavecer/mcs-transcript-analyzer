export interface PageResult<T> {
  data?: T[];
  error?: unknown;
  skipToken?: string;
  success?: boolean;
}

export async function loadAllPages<T>(
  getPage: (skipToken: string | undefined, pageSize: number) => Promise<PageResult<T>>,
  pageSize = 500,
  maxPages = 100,
): Promise<T[]> {
  const rows: T[] = [];
  const seenTokens = new Set<string>();
  let skipToken: string | undefined;

  for (let pageNumber = 0; pageNumber < maxPages; pageNumber += 1) {
    const page = await getPage(skipToken, pageSize);
    if (page.success === false) throw page.error ?? new Error("Dataverse page request failed.");
    rows.push(...(page.data ?? []));

    const nextToken = page.skipToken;
    if (!nextToken) return rows;
    if (seenTokens.has(nextToken)) throw new Error("Dataverse returned a repeated paging token.");
    seenTokens.add(nextToken);
    skipToken = nextToken;
  }

  throw new Error(`Dataverse result exceeded the ${maxPages * pageSize} row reporting limit.`);
}