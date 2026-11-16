import { describe, expect, it } from "vitest";
import { type MemoFilter } from "@/contexts/MemoFilterContext";
import { toggleTagFilter } from "@/lib/tag-facets";

describe("toggleTagFilter", () => {
  it("combines topic, source, status, and content search", () => {
    const search: MemoFilter = { factor: "contentSearch", value: "agent" };
    const topic = toggleTagFilter([search], "tema/ai-agentai");
    const source = toggleTagFilter(topic, "github");
    const status = toggleTagFilter(source, "busena/nauja");
    expect(status).toEqual([
      search,
      { factor: "tagSearch", value: "tema/ai-agentai" },
      { factor: "tagSearch", value: "github" },
      { factor: "tagSearch", value: "busena/nauja" },
    ]);
  });

  it("replaces a choice within a facet and toggles it off", () => {
    const initial: MemoFilter[] = [
      { factor: "tagSearch", value: "tema/ai-agentai" },
      { factor: "tagSearch", value: "github" },
    ];
    const changed = toggleTagFilter(initial, "tema/infrastruktura");
    expect(changed).toEqual([
      { factor: "tagSearch", value: "github" },
      { factor: "tagSearch", value: "tema/infrastruktura" },
    ]);
    expect(toggleTagFilter(changed, "tema/infrastruktura")).toEqual([{ factor: "tagSearch", value: "github" }]);
  });
});
