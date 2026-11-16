import type { MemoFilter } from "@/contexts/MemoFilterContext";

/** Tags in different facets may be combined; a new choice replaces only its own facet. */
export const getTagFacet = (tag: string): string => {
  if (tag.startsWith("tema/")) return "tema";
  if (tag.startsWith("busena/")) return "busena";
  if (tag === "github" || tag === "twitterX") return "source";
  return "other";
};

export const toggleTagFilter = (filters: MemoFilter[], tag: string): MemoFilter[] => {
  const active = filters.some((filter) => filter.factor === "tagSearch" && filter.value === tag);
  const facet = getTagFacet(tag);
  const remaining = filters.filter((filter) => filter.factor !== "tagSearch" || getTagFacet(filter.value) !== facet);
  return active ? remaining : [...remaining, { factor: "tagSearch", value: tag }];
};
