from __future__ import annotations

import csv
from pathlib import Path

import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise
import cluster_top500_fixed_threshold_series_intact as series


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories" / "top500_threshold_reports_90_to70"
OVERVIEW_MD = OUT_DIR / "README.md"
OVERVIEW_TSV = OUT_DIR / "overview.tsv"

THRESHOLDS = [value / 100.0 for value in range(90, 69, -1)]
TOP_TAGS_PER_CLUSTER = 20


def cluster_line(cluster: series.Cluster, rows: list[dict[str, object]], total_count: int, top500_count: int) -> str:
    return (
        f"{cluster.count} mentions "
        f"({cluster.count / total_count * 100.0:.4f}% full, "
        f"{cluster.count / top500_count * 100.0:.4f}% top500), "
        f"{len(cluster.members)} tags, "
        f"unweighted coherence {series.unweighted_internal_coherence(cluster, rows) * 100.0:.2f}%, "
        f"weighted coherence {series.weighted_internal_coherence(cluster, rows) * 100.0:.2f}%"
    )


def top_tags(cluster: series.Cluster, rows: list[dict[str, object]]) -> list[str]:
    ordered = sorted(
        cluster.members,
        key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
    )[:TOP_TAGS_PER_CLUSTER]
    return [f"{rows[idx]['coarse_tag']} ({rows[idx]['count']})" for idx in ordered]


def write_threshold_report(
    threshold: float,
    clusters: list[series.Cluster],
    log: list[dict[str, object]],
    rows: list[dict[str, object]],
    total_count: int,
    top500_count: int,
) -> Path:
    threshold_pct = int(round(threshold * 100.0))
    path = OUT_DIR / f"threshold_{threshold_pct:02d}.md"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"# Top-500 Fixed {threshold_pct}% Threshold\n\n")
        handle.write(
            "Centroids are unweighted means of member tag vectors. "
            "This run starts from the same top-500 frequency tags and repeatedly merges "
            f"non-overlapping centroid pairs with cosine similarity >= {threshold_pct}% until equilibrium. "
            "There is no forced collapse target.\n\n"
        )
        handle.write("## Summary\n\n")
        handle.write(f"- Threshold: {threshold_pct}%\n")
        handle.write(f"- Final clusters: {len(clusters)}\n")
        handle.write(f"- Passes: {log[-1]['pass']}\n")
        handle.write(f"- Top-10 coverage: {series.coverage(clusters, total_count, 10):.4f}% of full total\n")
        handle.write(f"- Top-25 coverage: {series.coverage(clusters, total_count, 25):.4f}% of full total\n")
        handle.write(f"- Top-50 coverage: {series.coverage(clusters, total_count, 50):.4f}% of full total\n")
        handle.write(f"- Top-500 selected coverage: {top500_count / total_count * 100.0:.4f}% of full total\n\n")

        handle.write("## Pass Log\n\n")
        handle.write("| pass | clusters | merged | top25 % full |\n")
        handle.write("|---:|---:|---:|---:|\n")
        for entry in log:
            merged = entry["merged"] if entry["merged"] != "" else ""
            handle.write(
                f"| {entry['pass']} | {entry['clusters']} | {merged} | "
                f"{float(entry['top25_pct']):.4f}% |\n"
            )
        handle.write("\n")

        handle.write("## Clusters\n\n")
        for rank, cluster in enumerate(clusters, start=1):
            handle.write(f"### {rank}. {cluster.anchor}\n\n")
            handle.write(f"{cluster_line(cluster, rows, total_count, top500_count)}\n\n")
            for tag in top_tags(cluster, rows):
                handle.write(f"- {tag}\n")
            handle.write("\n")
    return path


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows, _unvectorized, total_count = pairwise.load_intact_rows()
    rows = sorted(all_rows, key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))[: series.TOP_N]
    top500_count = sum(int(row["count"]) for row in rows)

    overview_rows: list[dict[str, object]] = []
    report_paths: list[tuple[int, Path]] = []

    for threshold in THRESHOLDS:
        clusters, log = series.run_threshold(rows, total_count, threshold)
        threshold_pct = int(round(threshold * 100.0))
        path = write_threshold_report(threshold, clusters, log, rows, total_count, top500_count)
        report_paths.append((threshold_pct, path))
        largest = clusters[0]
        overview_rows.append(
            {
                "threshold_pct": threshold_pct,
                "clusters": len(clusters),
                "passes": log[-1]["pass"],
                "top10_pct": f"{series.coverage(clusters, total_count, 10):.6f}",
                "top25_pct": f"{series.coverage(clusters, total_count, 25):.6f}",
                "top50_pct": f"{series.coverage(clusters, total_count, 50):.6f}",
                "largest_anchor": largest.anchor,
                "largest_pct_total": f"{largest.count / total_count * 100.0:.6f}",
                "largest_member_count": len(largest.members),
                "largest_unweighted_coherence_pct": f"{series.unweighted_internal_coherence(largest, rows) * 100.0:.2f}",
                "largest_weighted_coherence_pct": f"{series.weighted_internal_coherence(largest, rows) * 100.0:.2f}",
            }
        )
        print(
            f"{threshold_pct}%: clusters={len(clusters)} passes={log[-1]['pass']} "
            f"top25={series.coverage(clusters, total_count, 25):.4f}% "
            f"largest={largest.anchor} {largest.count / total_count * 100.0:.4f}%"
        )

    with OVERVIEW_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "threshold_pct",
                "clusters",
                "passes",
                "top10_pct",
                "top25_pct",
                "top50_pct",
                "largest_anchor",
                "largest_pct_total",
                "largest_member_count",
                "largest_unweighted_coherence_pct",
                "largest_weighted_coherence_pct",
            ],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(overview_rows)

    with OVERVIEW_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Top-500 Threshold Reports, 90% To 70%\n\n")
        handle.write(
            "Each file is a separate fixed-threshold run from the same top-500 frequency tag set. "
            "No threshold lowering happens inside a report, and no target cluster count is forced.\n\n"
        )
        handle.write("| threshold | clusters | top25 % | largest cluster | report |\n")
        handle.write("|---:|---:|---:|---|---|\n")
        by_threshold = {row["threshold_pct"]: row for row in overview_rows}
        for threshold_pct, path in report_paths:
            row = by_threshold[threshold_pct]
            rel = path.name
            handle.write(
                f"| {threshold_pct}% | {row['clusters']} | {float(row['top25_pct']):.4f}% | "
                f"{row['largest_anchor']} ({float(row['largest_pct_total']):.4f}%) | "
                f"[{rel}]({rel}) |\n"
            )

    print(f"reports_dir={OUT_DIR}")
    print(f"overview_md={OVERVIEW_MD}")
    print(f"overview_tsv={OVERVIEW_TSV}")


if __name__ == "__main__":
    main()
