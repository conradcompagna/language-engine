from flask import Flask, request
import json
from hanzipy.decomposer import HanziDecomposer

app = Flask(__name__)

print("[DEBUG] Loading HanziDecomposer...")
decomposer = HanziDecomposer()
print("[DEBUG] HanziDecomposer ready.")


def is_hanzi(ch: str) -> bool:
    return '\u4e00' <= ch <= '\u9fff'


def full_tree(ch: str, depth=0, visited=None):
    if visited is None:
        visited = set()

    if ch in visited:
        return {
            "char": ch,
            "note": "cycle_detected"
        }

    if depth > 20:
        return {
            "char": ch,
            "note": "max_depth_reached"
        }

    node = {
        "char": ch,
        "depth": depth
    }

    try:
        raw = decomposer.characters.get(ch)
    except Exception as e:
        return {
            "char": ch,
            "error": str(e)
        }

    if not raw:
        node["note"] = "no_decomposition_data"
        return node

    node["decomposition_type"] = raw.get("decomposition_type")
    node["components"] = raw.get("components", [])

    try:
        node["once"] = decomposer.decompose(ch, 1).get("components", [])
    except Exception:
        node["once"] = []

    try:
        node["radical"] = decomposer.decompose(ch, 2).get("components", [])
    except Exception:
        node["radical"] = []

    try:
        node["graphical"] = decomposer.decompose(ch, 3).get("components", [])
    except Exception:
        node["graphical"] = []

    children = []
    for comp in raw.get("components", []):
        comp = str(comp).strip()
        if is_hanzi(comp):
            children.append(
                full_tree(comp, depth + 1, visited | {ch})
            )

    if children:
        node["children"] = children

    return node


@app.route("/")
def index():
    return """
    <h2>Hanzi Full Decomposition Debug</h2>
    <form method="GET" action="/debug">
        <input name="text" placeholder="Enter Hanzi or word" style="width:300px;font-size:16px;">
        <button type="submit">Decompose</button>
    </form>
    """


@app.route("/debug")
def debug():
    text = request.args.get("text", "")

    if not text:
        return "<p>No input provided.</p><a href='/'>Back</a>"

    results = []
    for ch in text:
        if is_hanzi(ch):
            results.append(full_tree(ch))

    return f"""
    <h3>Input: {text}</h3>
    <pre style="white-space:pre-wrap;font-size:14px;">
{json.dumps(results, ensure_ascii=False, indent=2)}
    </pre>
    <br><a href="/">Back</a>
    """


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
