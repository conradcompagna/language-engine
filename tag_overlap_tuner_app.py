import csv
import json
import math
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

import numpy as np
from flask import Flask, Response, render_template_string, request
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize

import tag_overlap_analysis as analysis


BASE_DIR = Path(__file__).resolve().parent
FASTTEXT_PAIRWISE = (
    BASE_DIR
    / "training"
    / "trankit_finerweb_prep"
    / "derived_fasttext_categories"
    / "finerweb_coarse_tag_pairwise_fasttext_similarity.tsv"
)

WIDTH = 1200
HEIGHT = 820

PALETTE = [
    "#2563eb", "#dc2626", "#16a34a", "#ca8a04", "#9333ea", "#0f766e",
    "#db2777", "#ea580c", "#0891b2", "#4d7c0f", "#be123c", "#475569",
    "#7c2d12", "#0369a1", "#a21caf", "#15803d", "#b45309", "#4f46e5",
]


app = Flask(__name__)


def clamp(value, low, high, cast=float):
    try:
        value = cast(value)
    except Exception:
        value = low
    return max(low, min(high, value))


def load_base():
    nodes, inventory = analysis.make_nodes()
    return nodes, inventory


NODES, INVENTORY = load_base()
LABEL_TO_INDEX = {analysis.norm(node["label"]): idx for idx, node in enumerate(NODES)}


def load_fasttext_matrix():
    matrix = np.zeros((len(NODES), len(NODES)), dtype=np.float32)
    np.fill_diagonal(matrix, 1.0)
    if not FASTTEXT_PAIRWISE.exists():
        return matrix, False

    with FASTTEXT_PAIRWISE.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            left = LABEL_TO_INDEX.get(analysis.norm(row.get("coarse_tag_a")))
            right = LABEL_TO_INDEX.get(analysis.norm(row.get("coarse_tag_b")))
            if left is None or right is None:
                continue
            try:
                score = float(row.get("similarity_pct") or 0.0) / 100.0
            except ValueError:
                score = 0.0
            matrix[left, right] = max(matrix[left, right], score)
            matrix[right, left] = max(matrix[right, left], score)
    return matrix, True


FASTTEXT_SIM, FASTTEXT_AVAILABLE = load_fasttext_matrix()
DOC_CACHE = {mode: [analysis.weighted_doc(node, INVENTORY, mode) for node in NODES] for mode in ("child_focused", "balanced", "coarse_heavy")}


def build_docs(mode):
    return DOC_CACHE[mode]


def keep_top_features(matrix, top_k):
    matrix = matrix.tocsr()
    data = []
    indices = []
    indptr = [0]
    for row_idx in range(matrix.shape[0]):
        start = matrix.indptr[row_idx]
        end = matrix.indptr[row_idx + 1]
        row_data = matrix.data[start:end]
        row_indices = matrix.indices[start:end]
        if row_data.size > top_k:
            keep_positions = np.argpartition(row_data, -top_k)[-top_k:]
            keep_positions = keep_positions[np.argsort(row_indices[keep_positions])]
            row_data = row_data[keep_positions]
            row_indices = row_indices[keep_positions]
        data.extend(row_data.tolist())
        indices.extend(row_indices.tolist())
        indptr.append(len(data))
    sparse = csr_matrix((data, indices, indptr), shape=matrix.shape)
    return normalize(sparse)


def one_level_louvain(adjacency, resolution):
    n_nodes = len(adjacency)
    communities = list(range(n_nodes))
    degrees = [sum(edges.values()) for edges in adjacency]
    totals = degrees[:]
    total_weight = sum(degrees) / 2.0
    if total_weight <= 0:
        return np.arange(n_nodes)

    order = list(range(n_nodes))
    rng = np.random.default_rng(919)
    for _ in range(60):
        rng.shuffle(order)
        moved = False
        for node in order:
            degree = degrees[node]
            if degree <= 0:
                continue
            old_comm = communities[node]
            neighbor_weights = defaultdict(float)
            for neighbor, weight in adjacency[node].items():
                neighbor_weights[communities[neighbor]] += weight

            totals[old_comm] -= degree
            best_comm = old_comm
            best_gain = 0.0
            for comm, weight_in_comm in neighbor_weights.items():
                gain = weight_in_comm - resolution * degree * totals[comm] / (2.0 * total_weight)
                if gain > best_gain + 1e-12:
                    best_gain = gain
                    best_comm = comm
            totals[best_comm] += degree
            if best_comm != old_comm:
                communities[node] = best_comm
                moved = True
        if not moved:
            break

    remap = {}
    compact = []
    for comm in communities:
        if comm not in remap:
            remap[comm] = len(remap)
        compact.append(remap[comm])
    return np.array(compact, dtype=int)


def build_knn_adjacency(sim, k, floor):
    adjacency = [defaultdict(float) for _ in range(sim.shape[0])]
    for source in range(sim.shape[0]):
        added = 0
        for target in np.argsort(sim[source])[::-1]:
            if source == target:
                continue
            score = float(sim[source, target])
            if score < floor:
                break
            weight = score * score
            adjacency[source][target] = max(adjacency[source][target], weight)
            adjacency[target][source] = max(adjacency[target][source], weight)
            added += 1
            if added >= k:
                break
    return [dict(row) for row in adjacency]


def cluster_terms(ids, feature_matrix, vectorizer):
    if not ids:
        return []
    values = np.asarray(feature_matrix[ids].mean(axis=0)).ravel()
    names = vectorizer.get_feature_names_out()
    chosen = []
    for idx in values.argsort()[::-1]:
        if values[idx] <= 0:
            break
        term = names[idx]
        if term.startswith("ph_"):
            term = term[3:].replace("_", " ")
        if any(term == other or term in other or other in term for other in chosen):
            continue
        chosen.append(term)
        if len(chosen) >= 5:
            break
    return chosen


def classical_mds(sim):
    distance = 1.0 - sim
    np.fill_diagonal(distance, 0.0)
    d2 = distance * distance
    n = d2.shape[0]
    identity = np.eye(n)
    ones = np.ones((n, n)) / n
    centered = -0.5 * (identity - ones) @ d2 @ (identity - ones)
    eigvals, eigvecs = np.linalg.eigh(centered)
    order = eigvals.argsort()[::-1]
    vals = np.maximum(eigvals[order[:2]], 0)
    coords = eigvecs[:, order[:2]] * np.sqrt(vals)
    if coords.shape[1] < 2:
        coords = np.pad(coords, ((0, 0), (0, 2 - coords.shape[1])))
    x = coords[:, 0]
    y = coords[:, 1]
    x_span = max(1e-9, float(x.max() - x.min()))
    y_span = max(1e-9, float(y.max() - y.min()))
    out = np.column_stack(
        [
            56 + ((x - x.min()) / x_span) * (WIDTH - 112),
            56 + ((y - y.min()) / y_span) * (HEIGHT - 112),
        ]
    )
    return out


def parse_params():
    params = {
        "mode": request.args.get("mode", "child_focused"),
        "top_features": clamp(request.args.get("top_features", 180), 20, 500, int),
        "max_df": clamp(request.args.get("max_df", 0.30), 0.05, 0.95, float),
        "min_df": clamp(request.args.get("min_df", 2), 1, 10, int),
        "ngram_max": clamp(request.args.get("ngram_max", 3), 1, 3, int),
        "fasttext_weight": clamp(request.args.get("fasttext_weight", 0.0), 0.0, 1.0, float),
        "k": clamp(request.args.get("k", 12), 2, 50, int),
        "floor": clamp(request.args.get("floor", 0.03), 0.0, 0.50, float),
        "resolution": clamp(request.args.get("resolution", 0.60), 0.05, 5.0, float),
        "method": request.args.get("method", "louvain"),
        "fixed_k": clamp(request.args.get("fixed_k", 32), 2, 180, int),
    }
    if params["mode"] not in {"child_focused", "balanced", "coarse_heavy"}:
        params["mode"] = "child_focused"
    if params["method"] not in {"louvain", "fixed"}:
        params["method"] = "louvain"
    if not FASTTEXT_AVAILABLE:
        params["fasttext_weight"] = 0.0
    return params


def cache_key(params):
    return json.dumps(params, sort_keys=True)


@lru_cache(maxsize=160)
def compute_payload(key):
    params = json.loads(key)
    docs = build_docs(params["mode"])
    vectorizer = TfidfVectorizer(
        min_df=params["min_df"],
        max_df=params["max_df"],
        sublinear_tf=True,
        ngram_range=(1, params["ngram_max"]),
        norm="l2",
    )
    feature_matrix = vectorizer.fit_transform(docs)
    sparse_matrix = keep_top_features(feature_matrix, params["top_features"])
    lexical_sim = cosine_similarity(sparse_matrix)
    sim = (1.0 - params["fasttext_weight"]) * lexical_sim + params["fasttext_weight"] * FASTTEXT_SIM
    np.fill_diagonal(sim, 1.0)
    sim = np.clip(sim, 0.0, 1.0)

    if params["method"] == "fixed":
        distance = 1.0 - sim
        np.fill_diagonal(distance, 0.0)
        tree = linkage(squareform(distance, checks=False), method="average")
        labels = fcluster(tree, t=params["fixed_k"], criterion="maxclust") - 1
        adjacency = build_knn_adjacency(sim, params["k"], params["floor"])
    else:
        adjacency = build_knn_adjacency(sim, params["k"], params["floor"])
        labels = one_level_louvain(adjacency, params["resolution"])

    clusters = defaultdict(list)
    for idx, label in enumerate(labels):
        clusters[int(label)].append(idx)

    summaries = []
    for cluster, ids in clusters.items():
        ordered = sorted(ids, key=lambda idx: NODES[idx]["rank"])
        summaries.append(
            {
                "cluster": int(cluster),
                "size": len(ids),
                "frequency": sum(NODES[idx]["frequency"] for idx in ids),
                "terms": cluster_terms(ids, sparse_matrix, vectorizer),
                "tags": [NODES[idx]["label"] for idx in ordered],
            }
        )
    summaries.sort(key=lambda row: (-row["frequency"], row["size"]))
    order_map = {row["cluster"]: idx for idx, row in enumerate(summaries)}

    coords = classical_mds(sim)
    max_freq = max(node["frequency"] for node in NODES)
    nodes = []
    for idx, node in enumerate(NODES):
        cluster_idx = order_map[int(labels[idx])]
        nodes.append(
            {
                "id": idx,
                "label": node["label"],
                "rank": node["rank"],
                "frequency": node["frequency"],
                "cluster": cluster_idx,
                "cluster_name": " / ".join(summaries[cluster_idx]["terms"][:3]) or f"Cluster {cluster_idx + 1}",
                "x": round(float(coords[idx, 0]), 2),
                "y": round(float(coords[idx, 1]), 2),
                "radius": round(4 + 18 * math.sqrt(node["frequency"] / max_freq), 2),
                "color": PALETTE[cluster_idx % len(PALETTE)],
            }
        )

    links = []
    seen = set()
    for source, edges in enumerate(adjacency):
        for target, weight in edges.items():
            key_pair = (min(source, target), max(source, target))
            if key_pair in seen:
                continue
            seen.add(key_pair)
            score = float(sim[source, target])
            links.append({"source": key_pair[0], "target": key_pair[1], "score": round(score, 4)})
    links.sort(key=lambda row: row["score"], reverse=True)
    links = links[:1600]

    metrics = compute_metrics(sim, labels, adjacency)
    for idx, row in enumerate(summaries):
        row["id"] = idx
        row["color"] = PALETTE[idx % len(PALETTE)]
        row["name"] = " / ".join(row["terms"][:4]) or f"Cluster {idx + 1}"

    return {
        "params": params,
        "stats": {
            "nodes": len(NODES),
            "links": len(links),
            "clusters": len(summaries),
            **metrics,
        },
        "nodes": nodes,
        "links": links,
        "clusters": summaries,
        "fasttext_available": FASTTEXT_AVAILABLE,
    }


def compute_metrics(sim, labels, adjacency):
    clusters = defaultdict(list)
    for idx, label in enumerate(labels):
        clusters[int(label)].append(idx)

    intra = []
    external = []
    retention = []
    cut_weight = 0.0
    total_weight = 0.0

    for ids in clusters.values():
        if len(ids) > 1:
            intra.append(float(np.mean([sim[i, j] for pos, i in enumerate(ids) for j in ids[pos + 1:]])))
        outside = [idx for idx in range(len(NODES)) if idx not in ids]
        if outside:
            external.append(max(float(np.mean([sim[i, j] for i in ids])) for j in outside))

    for source, edges in enumerate(adjacency):
        ranked = sorted(edges.items(), key=lambda item: item[1], reverse=True)[:10]
        if ranked:
            retention.append(sum(1 for target, _ in ranked if labels[target] == labels[source]) / len(ranked))
        for target, weight in edges.items():
            if target <= source:
                continue
            total_weight += weight
            if labels[target] != labels[source]:
                cut_weight += weight

    sizes = [len(ids) for ids in clusters.values()]
    return {
        "largest_cluster": max(sizes) if sizes else 0,
        "mean_intra": round(float(np.mean(intra)), 4) if intra else 0.0,
        "mean_external": round(float(np.mean(external)), 4) if external else 0.0,
        "top10_retention": round(float(np.mean(retention)), 4) if retention else 0.0,
        "cut_ratio": round(float(cut_weight / total_weight), 4) if total_weight else 0.0,
    }


@app.route("/")
def index():
    return render_template_string(INDEX_HTML, fasttext_available=FASTTEXT_AVAILABLE)


@app.route("/api/cluster")
def cluster_api():
    params = parse_params()
    payload = compute_payload(cache_key(params))
    return Response(json.dumps(payload, ensure_ascii=False, default=json_default), mimetype="application/json")


def json_default(value):
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


INDEX_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tag Overlap Tuner</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #64748b;
      --line: #d8dee8;
      --accent: #2563eb;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    .app {
      display: grid;
      grid-template-columns: 320px minmax(560px, 1fr) 390px;
      min-height: 100vh;
    }
    aside {
      background: var(--panel);
      padding: 18px;
      max-height: 100vh;
      overflow: auto;
    }
    .left { border-right: 1px solid var(--line); }
    .right { border-left: 1px solid var(--line); }
    main {
      position: relative;
      min-height: 100vh;
      overflow: hidden;
      background:
        linear-gradient(90deg, rgba(23, 32, 51, 0.045) 1px, transparent 1px),
        linear-gradient(180deg, rgba(23, 32, 51, 0.045) 1px, transparent 1px);
      background-size: 40px 40px;
    }
    h1 { font-size: 20px; margin: 0 0 8px; }
    h2 {
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      margin: 20px 0 8px;
    }
    p { color: var(--muted); font-size: 13px; line-height: 1.45; margin: 0 0 12px; }
    label {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      font-size: 12px;
      color: var(--muted);
      font-weight: 650;
      margin: 12px 0 5px;
    }
    .tip {
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 16px;
      height: 16px;
      margin-left: 5px;
      border: 1px solid var(--line);
      border-radius: 50%;
      color: var(--muted);
      background: #fff;
      font-size: 11px;
      font-weight: 800;
      cursor: help;
      vertical-align: 1px;
    }
    .tip::after {
      content: attr(data-tip);
      position: absolute;
      left: 50%;
      bottom: calc(100% + 8px);
      transform: translateX(-50%);
      width: min(280px, 70vw);
      padding: 9px 10px;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      background: #111827;
      color: #fff;
      font-size: 12px;
      font-weight: 500;
      line-height: 1.35;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.22);
      opacity: 0;
      pointer-events: none;
      z-index: 20;
      white-space: normal;
    }
    .tip::before {
      content: "";
      position: absolute;
      left: 50%;
      bottom: calc(100% + 2px);
      transform: translateX(-50%);
      border: 6px solid transparent;
      border-top-color: #111827;
      opacity: 0;
      pointer-events: none;
      z-index: 21;
    }
    .tip:hover::after,
    .tip:focus::after,
    .tip:hover::before,
    .tip:focus::before {
      opacity: 1;
    }
    input[type="range"], select {
      width: 100%;
    }
    select {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      font-size: 13px;
    }
    input[type="range"] { accent-color: var(--accent); }
    .stats {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin: 14px 0;
    }
    .stat {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfe;
      padding: 9px;
    }
    .stat strong { display: block; font-size: 17px; }
    .stat span { color: var(--muted); font-size: 11px; }
    .toolbar {
      position: absolute;
      top: 14px;
      left: 14px;
      z-index: 3;
      display: flex;
      gap: 8px;
    }
    button {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      font-size: 13px;
      padding: 8px 10px;
      cursor: pointer;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
    }
    .icon-button {
      width: 36px;
      height: 34px;
      padding: 0;
      font-size: 18px;
      font-weight: 750;
    }
    .reset-button {
      width: 100%;
      margin-top: 14px;
      background: #f8fafc;
    }
    #graph {
      width: 100%;
      height: 100vh;
      display: block;
      cursor: grab;
    }
    #graph.panning { cursor: grabbing; }
    .link {
      stroke: #94a3b8;
      stroke-opacity: 0.18;
      stroke-linecap: round;
    }
    .node circle {
      stroke: #fff;
      stroke-width: 1.8;
      cursor: pointer;
    }
    .node text {
      font-size: 10px;
      fill: #172033;
      stroke: rgba(255, 255, 255, 0.9);
      stroke-width: 3px;
      paint-order: stroke;
      pointer-events: none;
      font-weight: 650;
    }
    .node.dim, .link.dim { opacity: 0.08; }
    .node.selected circle { stroke: #111827; stroke-width: 3px; }
    .cluster {
      border-bottom: 1px solid #edf1f6;
      padding: 8px 0;
      cursor: pointer;
      font-size: 12px;
    }
    .cluster strong {
      display: block;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .cluster span { color: var(--muted); }
    .swatch {
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      margin-right: 6px;
    }
    .tag-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
      max-height: 360px;
      overflow: auto;
    }
    .tag {
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 7px;
      padding: 5px 7px;
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .loading {
      position: absolute;
      right: 16px;
      top: 16px;
      color: var(--muted);
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 7px 9px;
      font-size: 12px;
      display: none;
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="left">
      <h1>Overlap Tuner</h1>
      <p>Adjust the statistical overlap model and recluster live. No precomputed region labels are used.</p>
      <p>fastText pairwise signal: <strong>{{ "available" if fasttext_available else "not found" }}</strong></p>

      <h2>Profile</h2>
      <label><span>Weighting mode <span class="tip" tabindex="0" data-tip="How each coarse tag profile is built. Child focused emphasizes the specific child part of slash labels; balanced keeps parent and child closer; coarse heavy makes the coarse label itself dominate.">?</span></span></label>
      <select id="mode">
        <option value="child_focused">child focused</option>
        <option value="balanced">balanced</option>
        <option value="coarse_heavy">coarse heavy</option>
      </select>

      <label><span>Top features <span class="tip" tabindex="0" data-tip="Number of strongest TF-IDF features kept per coarse tag. Lower values remove generic overlap and make tighter clusters; higher values keep more evidence but can create broad hubs.">?</span></span><output id="top_featuresOut">180</output></label>
      <input id="top_features" type="range" min="20" max="500" step="10" value="180">

      <label><span>Max document frequency <span class="tip" tabindex="0" data-tip="Drops terms that appear in too many tag profiles. Lower values suppress generic words more aggressively; higher values allow broader shared vocabulary.">?</span></span><output id="max_dfOut">0.30</output></label>
      <input id="max_df" type="range" min="0.05" max="0.95" step="0.01" value="0.30">

      <label><span>Min document frequency <span class="tip" tabindex="0" data-tip="Drops terms that appear in fewer than this many coarse-tag profiles. 1 keeps rare evidence; higher values reduce noise but can erase useful narrow labels.">?</span></span><output id="min_dfOut">2</output></label>
      <input id="min_df" type="range" min="1" max="10" step="1" value="2">

      <label><span>N-gram max <span class="tip" tabindex="0" data-tip="Maximum phrase length used by TF-IDF. 1 uses single words only; 2-3 keeps phrases such as government agency, football player, and monetary value.">?</span></span></label>
      <select id="ngram_max">
        <option value="1">1</option>
        <option value="2">2</option>
        <option value="3" selected>3</option>
      </select>

      <label><span>fastText blend <span class="tip" tabindex="0" data-tip="Blends semantic vector similarity into lexical overlap. 0 is pure overlap. Small values smooth synonyms; large values may merge NER-distinct but semantically related tags.">?</span></span><output id="fasttext_weightOut">0.00</output></label>
      <input id="fasttext_weight" type="range" min="0" max="1" step="0.05" value="0">

      <h2>Graph</h2>
      <label><span>Neighbors per tag <span class="tip" tabindex="0" data-tip="How many nearest neighbors each tag contributes to the graph. Lower values fragment into tighter local groups; higher values merge regions through more edges.">?</span></span><output id="kOut">12</output></label>
      <input id="k" type="range" min="2" max="50" step="1" value="12">

      <label><span>Similarity floor <span class="tip" tabindex="0" data-tip="Minimum similarity required to keep an edge. Raising it removes weak bridges and tightens clusters; lowering it connects more of the graph.">?</span></span><output id="floorOut">0.03</output></label>
      <input id="floor" type="range" min="0" max="0.5" step="0.01" value="0.03">

      <label><span>Resolution <span class="tip" tabindex="0" data-tip="Granularity for Louvain graph clustering. Lower usually gives fewer larger communities; higher usually gives more smaller communities.">?</span></span><output id="resolutionOut">0.60</output></label>
      <input id="resolution" type="range" min="0.05" max="5" step="0.05" value="0.60">

      <label><span>Method <span class="tip" tabindex="0" data-tip="Louvain discovers natural graph communities. Fixed-k hierarchical forces exactly the chosen number of clusters, which is useful for target-label experiments but can create awkward merges.">?</span></span></label>
      <select id="method">
        <option value="louvain">Louvain graph communities</option>
        <option value="fixed">Fixed-k hierarchical</option>
      </select>

      <label><span>Fixed cluster count <span class="tip" tabindex="0" data-tip="Only used by fixed-k hierarchical mode. Sets the exact number of clusters, regardless of whether the data naturally wants that many.">?</span></span><output id="fixed_kOut">32</output></label>
      <input id="fixed_k" type="range" min="2" max="180" step="1" value="32">

      <button id="resetSettings" class="reset-button">Reset settings</button>
    </aside>

    <main>
      <div class="toolbar">
        <button id="zoomOut" class="icon-button">-</button>
        <button id="zoomIn" class="icon-button">+</button>
        <button id="fit">Fit</button>
      </div>
      <div id="loading" class="loading">computing...</div>
      <svg id="graph">
        <g id="viewport">
          <g id="links"></g>
          <g id="nodes"></g>
        </g>
      </svg>
    </main>

    <aside class="right">
      <h2>Metrics</h2>
      <div class="stats">
        <div class="stat"><strong id="clusterCount">...</strong><span>clusters</span></div>
        <div class="stat"><strong id="largestCluster">...</strong><span>largest</span></div>
        <div class="stat"><strong id="cutRatio">...</strong><span>cut ratio</span></div>
      </div>
      <div class="stats">
        <div class="stat"><strong id="intra">...</strong><span>intra</span></div>
        <div class="stat"><strong id="external">...</strong><span>external</span></div>
        <div class="stat"><strong id="retention">...</strong><span>retention</span></div>
      </div>
      <h2>Selected</h2>
      <div id="details"><p>Select a node or cluster.</p></div>
      <h2>Clusters</h2>
      <div id="clusterList"></div>
    </aside>
  </div>

  <script>
    const controls = ["mode", "top_features", "max_df", "min_df", "ngram_max", "fasttext_weight", "k", "floor", "resolution", "method", "fixed_k"];
    const numericOutputs = ["top_features", "max_df", "min_df", "fasttext_weight", "k", "floor", "resolution", "fixed_k"];
    const defaults = {
      mode: "child_focused",
      top_features: "180",
      max_df: "0.30",
      min_df: "2",
      ngram_max: "3",
      fasttext_weight: "0",
      k: "12",
      floor: "0.03",
      resolution: "0.60",
      method: "louvain",
      fixed_k: "32"
    };
    const state = { data: null, selectedCluster: null, selectedNode: null, transform: { x: 0, y: 0, k: 1 } };
    const svg = document.getElementById("graph");
    const viewport = document.getElementById("viewport");
    const linksLayer = document.getElementById("links");
    const nodesLayer = document.getElementById("nodes");
    const loading = document.getElementById("loading");
    const fmt = new Intl.NumberFormat();
    let timer = null;

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" })[ch]);
    }

    function params() {
      const query = new URLSearchParams();
      for (const id of controls) query.set(id, document.getElementById(id).value);
      return query;
    }

    function syncOutputs() {
      for (const id of numericOutputs) {
        const out = document.getElementById(id + "Out");
        if (out) out.textContent = document.getElementById(id).value;
      }
    }

    function scheduleLoad() {
      syncOutputs();
      clearTimeout(timer);
      timer = setTimeout(load, 180);
    }

    async function load() {
      loading.style.display = "block";
      const response = await fetch("/api/cluster?" + params().toString());
      state.data = await response.json();
      state.selectedCluster = null;
      state.selectedNode = null;
      render();
      loading.style.display = "none";
    }

    function applyTransform() {
      viewport.setAttribute("transform", `translate(${state.transform.x} ${state.transform.y}) scale(${state.transform.k})`);
    }

    function fit() {
      const rect = svg.getBoundingClientRect();
      const xs = state.data.nodes.map(node => node.x);
      const ys = state.data.nodes.map(node => node.y);
      const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
      const spanX = Math.max(1, maxX - minX + 120);
      const spanY = Math.max(1, maxY - minY + 120);
      const scale = Math.min(rect.width / spanX, rect.height / spanY) * 0.96;
      state.transform = {
        k: scale,
        x: rect.width / 2 - ((minX + maxX) / 2) * scale,
        y: rect.height / 2 - ((minY + maxY) / 2) * scale
      };
      applyTransform();
    }

    function zoomBy(factor) {
      const rect = svg.getBoundingClientRect();
      const px = rect.width / 2, py = rect.height / 2;
      const oldK = state.transform.k;
      const newK = Math.max(0.08, Math.min(14, oldK * factor));
      const gx = (px - state.transform.x) / oldK;
      const gy = (py - state.transform.y) / oldK;
      state.transform.x = px - gx * newK;
      state.transform.y = py - gy * newK;
      state.transform.k = newK;
      applyTransform();
    }

    function render() {
      const data = state.data;
      document.getElementById("clusterCount").textContent = fmt.format(data.stats.clusters);
      document.getElementById("largestCluster").textContent = fmt.format(data.stats.largest_cluster);
      document.getElementById("cutRatio").textContent = data.stats.cut_ratio.toFixed(3);
      document.getElementById("intra").textContent = data.stats.mean_intra.toFixed(3);
      document.getElementById("external").textContent = data.stats.mean_external.toFixed(3);
      document.getElementById("retention").textContent = data.stats.top10_retention.toFixed(3);

      linksLayer.innerHTML = "";
      nodesLayer.innerHTML = "";
      for (const link of data.links) {
        const source = data.nodes[link.source];
        const target = data.nodes[link.target];
        const el = document.createElementNS("http://www.w3.org/2000/svg", "line");
        el.classList.add("link");
        el.setAttribute("x1", source.x);
        el.setAttribute("y1", source.y);
        el.setAttribute("x2", target.x);
        el.setAttribute("y2", target.y);
        el.setAttribute("stroke-width", String(0.5 + link.score * 4));
        linksLayer.appendChild(el);
      }

      for (const node of data.nodes) {
        const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
        group.classList.add("node");
        group.dataset.id = node.id;
        group.dataset.cluster = node.cluster;
        group.setAttribute("transform", `translate(${node.x} ${node.y})`);

        const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        circle.setAttribute("r", node.radius);
        circle.setAttribute("fill", node.color);
        const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
        title.textContent = `${node.label} | ${node.cluster_name}`;
        circle.appendChild(title);

        const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
        text.setAttribute("x", node.radius + 4);
        text.setAttribute("y", "4");
        text.textContent = node.rank <= 40 ? node.label : "";

        group.appendChild(circle);
        group.appendChild(text);
        group.addEventListener("click", event => {
          event.stopPropagation();
          selectNode(node.id);
        });
        nodesLayer.appendChild(group);
      }

      renderClusters();
      fit();
    }

    function renderClusters() {
      const list = document.getElementById("clusterList");
      list.innerHTML = state.data.clusters.map(cluster => `
        <div class="cluster" data-cluster="${cluster.id}">
          <strong><span class="swatch" style="background:${cluster.color}"></span>${escapeHtml(cluster.name)}</strong>
          <span>${cluster.size} tags | ${fmt.format(cluster.frequency)}</span>
        </div>
      `).join("");
      list.querySelectorAll("[data-cluster]").forEach(el => {
        el.addEventListener("click", () => selectCluster(Number(el.dataset.cluster)));
      });
    }

    function selectNode(id) {
      const node = state.data.nodes.find(item => item.id === id);
      state.selectedNode = id;
      state.selectedCluster = node.cluster;
      const cluster = state.data.clusters[node.cluster];
      document.getElementById("details").innerHTML = `
        <h1>${escapeHtml(node.label)}</h1>
        <p>Cluster: ${escapeHtml(cluster.name)}</p>
        <p>Rank ${node.rank}; frequency ${fmt.format(node.frequency)}</p>
      `;
      applySelection();
    }

    function selectCluster(id) {
      state.selectedCluster = id;
      state.selectedNode = null;
      const cluster = state.data.clusters[id];
      document.getElementById("details").innerHTML = `
        <h1>${escapeHtml(cluster.name)}</h1>
        <p>${cluster.size} tags; total frequency ${fmt.format(cluster.frequency)}</p>
        <div class="tag-list">${cluster.tags.map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>
      `;
      applySelection();
    }

    function applySelection() {
      for (const node of nodesLayer.children) {
        const selected = state.selectedCluster == null || Number(node.dataset.cluster) === state.selectedCluster;
        node.classList.toggle("dim", !selected);
        node.classList.toggle("selected", Number(node.dataset.id) === state.selectedNode);
      }
    }

    for (const id of controls) document.getElementById(id).addEventListener("input", scheduleLoad);
    document.getElementById("resetSettings").addEventListener("click", () => {
      for (const [id, value] of Object.entries(defaults)) {
        document.getElementById(id).value = value;
      }
      scheduleLoad();
    });
    document.getElementById("zoomIn").addEventListener("click", () => zoomBy(1.35));
    document.getElementById("zoomOut").addEventListener("click", () => zoomBy(1 / 1.35));
    document.getElementById("fit").addEventListener("click", fit);

    let dragging = false, last = null;
    svg.addEventListener("pointerdown", event => {
      if (event.target.closest(".node")) return;
      dragging = true;
      last = { x: event.clientX, y: event.clientY };
      svg.classList.add("panning");
      svg.setPointerCapture(event.pointerId);
    });
    svg.addEventListener("pointermove", event => {
      if (!dragging) return;
      state.transform.x += event.clientX - last.x;
      state.transform.y += event.clientY - last.y;
      last = { x: event.clientX, y: event.clientY };
      applyTransform();
    });
    svg.addEventListener("pointerup", event => {
      dragging = false;
      svg.classList.remove("panning");
      try { svg.releasePointerCapture(event.pointerId); } catch (err) {}
    });
    svg.addEventListener("wheel", event => {
      event.preventDefault();
      zoomBy(event.deltaY < 0 ? 1.12 : 0.89);
    }, { passive: false });

    syncOutputs();
    load();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5062, debug=False)
