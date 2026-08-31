import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "figma-node.json"
with open(path, encoding="utf-8") as f:
    d = json.load(f)

node = d["nodes"]["0:1"]["document"]


def walk(n, depth=0, max_depth=6):
    if depth > max_depth:
        return
    t = n.get("type", "")
    name = n.get("name", "")
    bb = n.get("absoluteBoundingBox") or {}
    w = bb.get("width", "")
    h = bb.get("height", "")
    chars = n.get("characters", "") if t == "TEXT" else ""
    layout = n.get("layoutMode", "")
    gap = n.get("itemSpacing", "")
    pad_l = n.get("paddingLeft", "")
    fills = n.get("fills", [])
    color = ""
    if fills and fills[0].get("type") == "SOLID":
        c = fills[0]["color"]
        color = f"rgb({int(c['r']*255)},{int(c['g']*255)},{int(c['b']*255)})"
    style = n.get("style", {})
    fs = style.get("fontSize", "")
    fw = style.get("fontWeight", "")
    line = "  " * depth + f"{t}: {name}"
    if chars:
        line += f" -> {chars[:100]}"
    if layout:
        line += f" [{layout} gap={gap} padL={pad_l}]"
    if w:
        line += f" ({w:.0f}x{h:.0f})"
    if color and depth < 4:
        line += f" {color}"
    if fs:
        line += f" font={fs}/{fw}"
    print(line)
    for ch in n.get("children", []):
        walk(ch, depth + 1, max_depth)


walk(node)
