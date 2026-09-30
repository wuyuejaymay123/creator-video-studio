"""Validate a filming plan and export narration and a matching shooting table.

Project helper for creator-video-studio 2.0. Python 3.10+, stdlib only.
This validates structure and references, not truth, performance, or aesthetics.
"""
import argparse
import json
import sys
from pathlib import Path

RELATIONS = {"hold", "contrast", "cause", "sequence", "correction", "zoom",
             "analogy", "summary", "evidence", "context"}
TECHNIQUES = {"cut", "occlusion", "whip", "match", "push", "pull",
              "graphic_handoff", "audio_bridge"}


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def string_list(value, allow_empty=True):
    return (isinstance(value, list) and (allow_empty or bool(value))
            and all(nonempty(item) for item in value))


def validate(plan):
    errors = []
    if not isinstance(plan, dict):
        return ["Plan must be a JSON object."]
    version = plan.get("schema_version")
    if type(version) is not int or version not in (1, 2):
        errors.append("schema_version must be integer 1 or 2.")
    if version == 2 or "brief" in plan:
        brief = plan.get("brief")
        if not isinstance(brief, dict):
            errors.append("brief is required for version 2.")
        else:
            for field in ("audience", "problem", "payoff", "action"):
                if not nonempty(brief.get(field)):
                    errors.append(f"brief.{field} must be nonempty text.")
    if not nonempty(plan.get("title")):
        errors.append("title must be nonempty text.")
    if not string_list(plan.get("assumptions", [])):
        errors.append("assumptions must be a list of nonempty strings.")
    segments, assets = plan.get("segments"), plan.get("assets", [])
    if not isinstance(segments, list) or not segments:
        errors.append("segments must be a nonempty list.")
        segments = []
    if not isinstance(assets, list):
        errors.append("assets must be a list.")
        assets = []
    segment_index, asset_ids = {}, set()
    for index, asset in enumerate(assets):
        label = f"assets[{index}]"
        if not isinstance(asset, dict):
            errors.append(f"{label} must be an object.")
            continue
        for field in ("id", "purpose", "source"):
            if not nonempty(asset.get(field)):
                errors.append(f"{label}.{field} must be nonempty text.")
        asset_id = asset.get("id")
        if "name" in asset and not nonempty(asset["name"]):
            errors.append(f"{label}.name must be nonempty text when provided.")
        if nonempty(asset_id):
            if asset_id in asset_ids:
                errors.append(f"Duplicate asset id: {asset_id}")
            asset_ids.add(asset_id)
        if asset.get("type") not in ("imagegen", "recording", "screenshot", "diagram", "audio"):
            errors.append(f"{label}.type is invalid.")
        if asset.get("status") not in ("planned", "available", "generated"):
            errors.append(f"{label}.status is invalid.")
        if asset.get("type") == "imagegen":
            if not nonempty(asset.get("prompt")):
                errors.append(f"{label}.prompt is required for imagegen.")
            if not string_list(asset.get("layers"), allow_empty=False):
                errors.append(f"{label}.layers must list image layers.")
            if type(asset.get("animate")) is not bool:
                errors.append(f"{label}.animate must be a boolean.")
            if asset.get("animate") is True:
                motion = asset.get("motion")
                if not isinstance(motion, dict):
                    errors.append(f"{label}.motion is required for animation.")
                else:
                    for field in ("before", "change", "after", "cue"):
                        if not nonempty(motion.get(field)):
                            errors.append(f"{label}.motion.{field} is required.")
    for index, segment in enumerate(segments):
        label = f"segments[{index}]"
        if not isinstance(segment, dict):
            errors.append(f"{label} must be an object.")
            continue
        for field in ("id", "speech", "delivery", "screen"):
            if not nonempty(segment.get(field)):
                errors.append(f"{label}.{field} must be nonempty text.")
        segment_id = segment.get("id")
        if nonempty(segment_id):
            if segment_id in segment_index:
                errors.append(f"Duplicate segment id: {segment_id}")
            segment_index[segment_id] = index
        if segment.get("visibility") not in ("face", "voice"):
            errors.append(f"{label}.visibility must be face or voice.")
        if version == 2 or "visual" in segment:
            if not nonempty(segment.get("purpose")):
                errors.append(f"{label}.purpose must describe why this line exists.")
            visual = segment.get("visual")
            if not isinstance(visual, dict):
                errors.append(f"{label}.visual must be an object.")
            else:
                if visual.get("relation") not in tuple(RELATIONS):
                    errors.append(f"{label}.visual.relation is invalid.")
                for field in ("object", "before", "change", "after", "cue", "hold"):
                    if not nonempty(visual.get(field)):
                        errors.append(f"{label}.visual.{field} must be nonempty text.")
        refs = segment.get("assets", [])
        if not string_list(refs):
            errors.append(f"{label}.assets must be a list of IDs.")
        else:
            for ref in refs:
                if ref not in asset_ids:
                    errors.append(f"{label} references missing asset: {ref}")
    transitions = plan.get("transitions", [] if version == 1 else None)
    if not isinstance(transitions, list):
        errors.append("transitions must be a list (empty if all boundaries use ordinary cuts/holds).")
        transitions = []
    transition_ids, boundaries = set(), set()
    for index, transition in enumerate(transitions):
        label = f"transitions[{index}]"
        if not isinstance(transition, dict):
            errors.append(f"{label} must be an object.")
            continue
        for field in ("id", "reason", "cue", "outgoing", "incoming", "continuity", "edit", "audio", "fallback"):
            if not nonempty(transition.get(field)):
                errors.append(f"{label}.{field} must be nonempty text.")
        transition_id = transition.get("id")
        if nonempty(transition_id):
            if transition_id in transition_ids:
                errors.append(f"Duplicate transition id: {transition_id}")
            transition_ids.add(transition_id)
        start, end = transition.get("from"), transition.get("to")
        valid_refs = all(nonempty(ref) and ref in segment_index for ref in (start, end))
        if not valid_refs:
            errors.append(f"{label} references a missing segment.")
        else:
            if segment_index[end] != segment_index[start] + 1:
                errors.append(f"{label} must connect adjacent forward segments.")
            boundary = (start, end)
            if boundary in boundaries:
                errors.append(f"{label} duplicates a boundary; combine its techniques in one execution card.")
            boundaries.add(boundary)
        if transition.get("technique") not in tuple(TECHNIQUES):
            errors.append(f"{label}.technique is invalid.")
        if transition.get("mode") not in ("capture", "post", "hybrid"):
            errors.append(f"{label}.mode must be capture, post or hybrid.")
        if transition.get("status") not in ("planned", "ready", "fallback"):
            errors.append(f"{label}.status is invalid.")
        if transition.get("status") == "ready" and not nonempty(transition.get("checked_media")):
            errors.append(f"{label}.checked_media must record the inspected media and cut points.")
    promises = plan.get("promises", [])
    if not isinstance(promises, list):
        errors.append("promises must be a list.")
        promises = []
    for index, promise in enumerate(promises):
        label = f"promises[{index}]"
        if not isinstance(promise, dict):
            errors.append(f"{label} must be an object.")
            continue
        if not nonempty(promise.get("text")):
            errors.append(f"{label}.text must describe the promise.")
        setup = promise.get("setup")
        if not nonempty(setup) or setup not in segment_index:
            errors.append(f"{label}.setup references a missing segment.")
        payoffs = promise.get("payoff")
        if not string_list(payoffs, allow_empty=False):
            errors.append(f"{label}.payoff must contain segment IDs.")
        else:
            for payoff in payoffs:
                if payoff not in segment_index:
                    errors.append(f"{label}.payoff references missing segment: {payoff}")
                elif nonempty(setup) and setup in segment_index and segment_index[payoff] < segment_index[setup]:
                    errors.append(f"{label}.payoff occurs before setup: {payoff}")
    takeaway = plan.get("takeaway")
    if takeaway is not None:
        if not isinstance(takeaway, dict):
            errors.append("takeaway must be an object.")
        else:
            if not nonempty(takeaway.get("title")):
                errors.append("takeaway.title must be nonempty text.")
            at = takeaway.get("segment")
            if not nonempty(at) or at not in segment_index:
                errors.append("takeaway.segment references a missing segment.")
            if not string_list(takeaway.get("items"), allow_empty=False):
                errors.append("takeaway.items must contain the actual takeaway text.")
    return errors


def cell(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("|", "&#124;").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>"))


def render(plan):
    narration = f"# {plan['title']}｜口播稿\n\n" + "\n\n".join(s["speech"] for s in plan["segments"]) + "\n"
    numbers = {s["id"]: str(i) for i, s in enumerate(plan["segments"], 1)}
    techniques = {
        "cut": "直接切到下一段", "occlusion": "遮住镜头，再切到下一段",
        "whip": "快速转动镜头，接到下一个画面", "match": "让前后两个画面接得上",
        "push": "把画面拉近", "pull": "把画面拉远",
        "graphic_handoff": "用你的动作带出图片", "audio_bridge": "说话继续，画面先换"}
    modes = {"capture": "需要你拍两段镜头，Codex 负责接起来",
             "post": "由 Codex 做画面，你按表录好声音即可",
             "hybrid": "你拍好动作，Codex 再配上图片和动画"}
    statuses = {"planned": "还没制作", "ready": "所需镜头已经检查",
                "fallback": "使用下面的备用做法", "available": "素材已提供", "generated": "素材已生成"}
    kinds = {"imagegen": "用 ImageGen 生成图片", "recording": "录屏",
             "screenshot": "截图", "diagram": "用代码画文字和图形", "audio": "声音素材"}
    lines = [f"# {plan['title']}｜照着拍的说明", "",
             "先看下面的拍摄表。标着“露脸”的句子，对着镜头说；标着“仅声音”的句子，只录声音。需要你提供截图或视频的地方见下方素材清单，Codex 收到后负责画面制作。",
             "", "普通口播时，手机或相机放稳，不用来回移动。需要额外动作的地方会单独写出来。", ""]
    if plan.get("brief"):
        brief = plan["brief"]
        lines.extend([f"这条视频讲给谁听：{brief['audience']}。", "",
                      f"希望观众看完能做到：{brief['payoff']}。", ""])
    lines.extend(["## 1. 你照着这张表拍", "",
                  "“你怎么说、怎么做”是拍摄提醒，不用读出来。", "",
                  "| 第几句 | 你要说的话 | 露脸/仅声音 | 你怎么说、怎么做 | 观众会看到什么 |",
                  "|---|---|---|---|---|"])
    for s in plan["segments"]:
        values = [numbers[s["id"]], s["speech"], "露脸" if s["visibility"] == "face" else "仅声音",
                  s["delivery"], s["screen"]]
        lines.append("| " + " | ".join(cell(x) for x in values) + " |")
    visuals = [s for s in plan["segments"] if "visual" in s and s["visibility"] == "voice"
               and s["visual"]["relation"] != "hold"]
    if visuals:
        lines.extend(["", "## 2. 图片会怎么动（由 Codex 制作）", "",
                      "你不用操作动画软件。下面是成片大致会呈现的样子；出现时间会按你的实际录音来调整。", ""])
        for s in visuals:
            v = s["visual"]
            lines.extend([f"### 第 {numbers[s['id']]} 句", "",
                          f"你说：“{s['speech']}”", "",
                          f"- 先看到：{v['before']}。", f"- 接着：{v['change']}。",
                          f"- 最后看到：{v['after']}。", f"- 什么时候动：{v['cue']}。",
                          f"- 留给观众看清楚的时间：{v['hold']}。", ""])
    lines.extend(["", "## 3. 两段画面怎么接", ""])
    if not plan.get("transitions"):
        lines.append("这里不需要特别的切换效果。把话自然说完，再接下一段就可以。")
    for t in plan.get("transitions", []):
        lines.extend([f"### 第 {numbers[t['from']]} 句接第 {numbers[t['to']]} 句：{techniques[t['technique']]}", "",
                      modes[t["mode"]] + "。", "", f"目前：{statuses[t['status']]}。", ""])
        for field, title in (("reason", "为什么这样接"), ("cue", "什么时候切换"),
                             ("outgoing", "前一段怎么拍或准备"), ("incoming", "后一段怎么拍或准备"),
                             ("continuity", "前后要注意什么"), ("edit", "Codex 怎么接"),
                             ("audio", "声音怎么接"), ("fallback", "如果接不上")):
            lines.append(f"- {title}：{t[field]}")
        if t.get("checked_media"):
            lines.append("- 已检查的镜头：" + t["checked_media"])
        lines.append("")
    pending_media = [a for a in plan.get("assets", [])
                     if a["type"] in ("screenshot", "recording") and a["status"] == "planned"]
    if pending_media:
        lines.extend(["", "## 需要你补充的截图或视频", "",
                      "下面这些画面还没有拿到，需要你补充；其他部分可以继续准备。", "",
                      "| 素材 | 对应口播 | 用来说明什么 | 具体怎么准备、缺少时怎么办 |",
                      "|---|---|---|---|"])
        for index, asset in enumerate(pending_media, 1):
            speeches = "；".join(s["speech"] for s in plan["segments"] if asset["id"] in s.get("assets", []))
            values = [asset.get("name", f"待补素材 {index}"), speeches or "通用素材", asset["purpose"], asset["source"]]
            lines.append("| " + " | ".join(cell(x) for x in values) + " |")
    if plan.get("assets"):
        lines.extend(["", "## 4. 需要准备哪些图片和素材", "",
                      "标着“还没制作”的素材，都是接下来要做的。出图和动画分开完成。", ""])
    for index, asset in enumerate(plan.get("assets", []), 1):
        name = asset.get("name", f"素材 {index}")
        lines.extend([f"### {name}", "", f"- 用来说明什么：{asset['purpose']}",
                      f"- 怎么准备：{kinds[asset['type']]}。目前{statuses[asset['status']]}。", ""])
        if asset["type"] == "imagegen":
            if asset["animate"]:
                lines.append("这组图片会交给 HyperFrames 做动画，具体效果见上面的画面说明。")
                lines.append("")
            lines.extend(["<details>", "<summary>给 Codex 的制图说明（拍摄时不用看）</summary>", "",
                          "图片要求：" + asset["prompt"], "",
                          "需要分别制作：" + "；".join(asset["layers"]), "",
                          "准备方式：" + asset["source"], ""])
            if asset["animate"]:
                motion = asset["motion"]
                lines.extend([f"动画过程：{motion['before']} → {motion['change']} → {motion['after']}。", "",
                              "配合哪句话或动作：" + motion["cue"], ""])
            lines.extend(["</details>", ""])
        else:
            lines.extend(["准备方式：" + asset["source"], ""])
    if plan.get("takeaway"):
        t = plan["takeaway"]
        lines.extend(["", "## 5. 结尾给观众保存的内容", "", f"在第 {numbers[t['segment']]} 句时显示：**{t['title']}**", ""])
        lines.extend(f"{i}. {item}" for i, item in enumerate(t["items"], 1))
    if plan.get("assumptions") or plan.get("promises"):
        lines.extend(["", "<details>", "<summary>补充说明与内容检查</summary>", ""])
        lines.extend("- " + x for x in plan.get("assumptions", []))
        for p in plan.get("promises", []):
            locations = "、".join(numbers[x] for x in p["payoff"])
            lines.append(f"- 开头让观众期待的内容：{p['text']}；在第 {locations} 句给出答案。")
        lines.extend(["", "</details>"])
    return narration, "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--out", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
        errors = validate(plan)
        if errors:
            print("INVALID\n" + "\n".join("- " + item for item in errors), file=sys.stderr)
            return 1
        if args.check:
            print(f"VALID: {len(plan['segments'])} segments; structural checks only.")
            return 0
        output = args.out.resolve()
        targets = [output / "口播稿.md", output / "拍摄与后期.md"]
        if args.plan.resolve() in targets:
            raise ValueError("Output must not replace the input plan.")
        if not args.overwrite and any(path.exists() for path in targets):
            raise ValueError("Output already exists. Choose another version directory or use --overwrite.")
        rendered = render(plan)
        output.mkdir(parents=True, exist_ok=True)
        for path, content in zip(targets, rendered):
            path.write_text(content, encoding="utf-8")
            print(path)
        return 0
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
