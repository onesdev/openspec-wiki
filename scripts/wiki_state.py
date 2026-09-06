#!/usr/bin/env python3
"""openspec-wiki 同步状态工具

职责边界：只做「确定性记账」，不做内容生成。
- plan   ：扫描 openspec/ 与 wiki/.wiki-manifest.json 账本，输出本次要做什么（JSON）。
- commit ：生成完成后，把已处理的 capability / change 记入账本。

增量机制（与账本联动）：
1. 每个已同步进 wiki 的变更（change）按 Change ID 记入 syncedChanges；
2. 每个已生成页面的能力（capability）按 spec.md 的 sha256 记入 specs；
3. 下次 plan 时：新归档变更 = 账本里没有的 archive 目录；能力页过期 = spec hash 变化
   （只比对哈希，不读内容）；缺页/被删除的能力也据此推断。
这样避免每次都让 LLM 重读全部 spec 做内容比对。

用法：
  python3 wiki_state.py plan <project_dir>
  python3 wiki_state.py commit <project_dir> [--caps a,b] [--change-ids x,y] \
      [--remove-caps a,b] [--overview]
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

MANIFEST_NAME = ".wiki-manifest.json"


def die(msg, code=1):
    print(json.dumps({"error": msg}, ensure_ascii=False))
    sys.exit(code)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_manifest(wiki_dir):
    path = os.path.join(wiki_dir, MANIFEST_NAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def save_manifest(wiki_dir, manifest):
    os.makedirs(wiki_dir, exist_ok=True)
    path = os.path.join(wiki_dir, MANIFEST_NAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")


def extract_change_id(change_dir):
    """依次尝试：proposal.md 的 Change ID 段 → .openspec.yaml 的 id/name → 目录名去日期前缀。"""
    proposal = os.path.join(change_dir, "proposal.md")
    text = read_text(proposal)
    m = re.search(r"##\s*Change ID\s*\n+\s*([^\s#][^\n]*)", text)
    if m:
        return m.group(1).strip()
    meta = os.path.join(change_dir, ".openspec.yaml")
    mtext = read_text(meta)
    m = re.search(r"^(?:id|name):\s*([^\s#]+)", mtext, re.MULTILINE)
    if m:
        return m.group(1).strip()
    base = os.path.basename(change_dir.rstrip("/"))
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", base)


def extract_capabilities(change_dir):
    """变更涉及的能力 = 变更内 delta specs 目录 ∪ proposal.md Capabilities 段中列出的能力（含 REMOVED）。"""
    caps = []
    spec_root = os.path.join(change_dir, "specs")
    if os.path.isdir(spec_root):
        for name in sorted(os.listdir(spec_root)):
            if os.path.isfile(os.path.join(spec_root, name, "spec.md")):
                caps.append(name)
    proposal = os.path.join(change_dir, "proposal.md")
    text = read_text(proposal)
    m = re.search(r"##\s*Capabilities\s*\n(.*?)(?=\n##\s|\Z)", text, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            cm = re.match(r"[-*]\s*`?([A-Za-z0-9][A-Za-z0-9_-]*)`?", line.strip())
            if cm and cm.group(1) not in caps:
                caps.append(cm.group(1))
    return caps


def scan_changes(openspec_dir):
    """返回 (archived, active)：每个元素 {id, dir(相对 openspec), date, capabilities}。"""
    changes_root = os.path.join(openspec_dir, "changes")
    archived_root = os.path.join(changes_root, "archive")
    date_re = re.compile(r"^(\d{4}-\d{2}-\d{2})")

    archived = []
    if os.path.isdir(archived_root):
        for name in sorted(os.listdir(archived_root)):
            cdir = os.path.join(archived_root, name)
            if not os.path.isdir(cdir):
                continue
            m = date_re.match(name)
            archived.append({
                "id": extract_change_id(cdir),
                "dir": os.path.join("changes", "archive", name),
                "date": m.group(1) if m else "",
                "capabilities": extract_capabilities(cdir),
            })

    active = []
    if os.path.isdir(changes_root):
        for name in sorted(os.listdir(changes_root)):
            if name == "archive":
                continue
            cdir = os.path.join(changes_root, name)
            if not os.path.isdir(cdir):
                continue
            active.append({
                "id": extract_change_id(cdir),
                "dir": os.path.join("changes", name),
                "date": "",
                "capabilities": extract_capabilities(cdir),
            })
    return archived, active


def overview_sources(project_dir, openspec_dir):
    """总览页事实源：openspec/project.md 优先，其次项目 README.md；config.yaml 始终参与哈希。"""
    proj_md = os.path.join(openspec_dir, "project.md")
    readme = os.path.join(project_dir, "README.md")
    if os.path.isfile(proj_md):
        return proj_md
    if os.path.isfile(readme):
        return readme
    return None


def overview_hash(project_dir, openspec_dir):
    src = overview_sources(project_dir, openspec_dir)
    h = hashlib.sha256()
    if src:
        with open(src, "rb") as f:
            h.update(f.read())
    config = os.path.join(openspec_dir, "config.yaml")
    if os.path.isfile(config):
        with open(config, "rb") as f:
            h.update(b"\x00--config--\x00")
            h.update(f.read())
    return h.hexdigest()


def list_capabilities(openspec_dir):
    spec_root = os.path.join(openspec_dir, "specs")
    caps = []
    if os.path.isdir(spec_root):
        for name in sorted(os.listdir(spec_root)):
            if os.path.isfile(os.path.join(spec_root, name, "spec.md")):
                caps.append(name)
    return caps


def cmd_plan(args):
    project_dir = os.path.abspath(args.project)
    openspec_dir = os.path.join(project_dir, "openspec")
    if not os.path.isdir(openspec_dir):
        die("项目目录下不存在 openspec/：%s" % project_dir)
    wiki_dir = os.path.join(project_dir, "wiki")
    manifest = load_manifest(wiki_dir)

    caps = list_capabilities(openspec_dir)
    archived, active = scan_changes(openspec_dir)

    synced_changes = (manifest or {}).get("syncedChanges", {})
    synced_specs = (manifest or {}).get("specs", {})

    pending = [c for c in archived
               if c["id"] not in synced_changes and c["dir"] not in
               {v.get("dir") for v in synced_changes.values()}]
    touched = {cap for c in pending for cap in c["capabilities"]}

    drifted = []
    if manifest:
        for cap in caps:
            recorded = synced_specs.get(cap, {}).get("hash")
            if recorded and recorded != sha256_file(os.path.join(openspec_dir, "specs", cap, "spec.md")):
                drifted.append(cap)

    missing_pages = [cap for cap in caps
                     if not os.path.isfile(os.path.join(wiki_dir, "specs", cap + ".md"))]
    removed = [cap for cap in sorted(synced_specs) if cap not in caps]

    if not manifest or not os.path.isfile(os.path.join(wiki_dir, "README.md")):
        mode = "full"
        to_generate = list(caps)
    else:
        mode = "incremental"
        to_generate = sorted(touched | set(drifted) | set(missing_pages))

    current_ohash = overview_hash(project_dir, openspec_dir)
    overview_dirty = (not manifest or not manifest.get("overviewSynced")
                      or manifest.get("overviewHash") != current_ohash)

    plan = {
        "project": project_dir,
        "wikiDir": wiki_dir,
        "mode": mode,
        "allCapabilities": caps,
        "capabilitiesToGenerate": to_generate,
        "driftedCapabilities": drifted,
        "missingPages": missing_pages,
        "capabilitiesRemoved": removed,
        "pendingChanges": pending,
        "activeChanges": active,
        "overviewDirty": overview_dirty,
        "changelogDirty": bool(pending),
        "stats": {
            "capabilities": len(caps),
            "archivedChanges": len(archived),
            "syncedChanges": len(synced_changes),
            "pendingChanges": len(pending),
        },
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))


def cmd_commit(args):
    project_dir = os.path.abspath(args.project)
    openspec_dir = os.path.join(project_dir, "openspec")
    if not os.path.isdir(openspec_dir):
        die("项目目录下不存在 openspec/：%s" % project_dir)
    wiki_dir = os.path.join(project_dir, "wiki")
    manifest = load_manifest(wiki_dir) or {
        "version": 1,
        "overviewSynced": False,
        "specs": {},
        "syncedChanges": {},
    }

    caps = [c for c in (args.caps or "").split(",") if c]
    for cap in caps:
        spec_file = os.path.join(openspec_dir, "specs", cap, "spec.md")
        if os.path.isfile(spec_file):
            manifest["specs"][cap] = {"hash": sha256_file(spec_file), "syncedAt": now_iso()}
        else:
            print("warn: capability 不存在，跳过：%s" % cap, file=sys.stderr)

    remove_caps = [c for c in (args.remove_caps or "").split(",") if c]
    for cap in remove_caps:
        manifest["specs"].pop(cap, None)

    change_ids = [c for c in (args.change_ids or "").split(",") if c]
    archived, active = scan_changes(openspec_dir)
    by_id = {c["id"]: c for c in archived + active}
    for cid in change_ids:
        change = by_id.get(cid)
        if not change:
            print("warn: change 不存在，跳过：%s" % cid, file=sys.stderr)
            continue
        manifest["syncedChanges"][cid] = {
            "dir": change["dir"],
            "capabilities": change["capabilities"],
            "syncedAt": now_iso(),
        }

    if args.overview:
        manifest["overviewSynced"] = True
        manifest["overviewHash"] = overview_hash(project_dir, openspec_dir)

    manifest["version"] = 1
    manifest["lastSyncAt"] = now_iso()
    save_manifest(wiki_dir, manifest)
    print(json.dumps({
        "ok": True,
        "committedCaps": caps,
        "removedCaps": remove_caps,
        "committedChanges": change_ids,
        "overview": bool(args.overview),
        "lastSyncAt": manifest["lastSyncAt"],
    }, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="openspec-wiki 同步状态工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="输出本次同步计划（JSON）")
    p_plan.add_argument("project", help="项目目录（须含 openspec/）")
    p_plan.set_defaults(func=cmd_plan)

    p_commit = sub.add_parser("commit", help="生成完成后记账")
    p_commit.add_argument("project", help="项目目录（须含 openspec/）")
    p_commit.add_argument("--caps", default="", help="本次(重)生成的能力，逗号分隔")
    p_commit.add_argument("--change-ids", default="", help="本次已写入 changelog 的变更 ID，逗号分隔")
    p_commit.add_argument("--remove-caps", default="", help="已从 wiki 删除页面的能力，逗号分隔")
    p_commit.add_argument("--overview", action="store_true", help="总览页本次已更新")
    p_commit.set_defaults(func=cmd_commit)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
