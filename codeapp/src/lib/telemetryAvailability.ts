export interface MetricLabels {
  singular: string;
  plural: string;
}

export function formatObservedMetric(
  value: number | null | undefined,
  labels: MetricLabels,
): string {
  if (value == null) return `${labels.plural} unavailable`;
  return `${value} ${value === 1 ? labels.singular : labels.plural}`;
}

export function formatObservedPair(
  first: number | null | undefined,
  firstLabels: MetricLabels,
  second: number | null | undefined,
  secondLabels: MetricLabels,
): string {
  if (first == null && second == null) return "Unavailable in this transcript";
  return `${formatObservedMetric(first, firstLabels)} / ${formatObservedMetric(second, secondLabels)}`;
}
