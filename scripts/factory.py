#!/usr/bin/env python3
"""State and dashboard for the software factory. Standard library only.

All state lives in <repo>/.factory/ (excluded from git via .git/info/exclude):
    backlog.md                 "- [ ] F03 item (deps: F01) [ui]"; "[~] ... -> <task id>" once taken,
                               [x] done, [-] dropped
    plan/                      analyst output: brief, questions, answers, proposed-backlog,
                               items/<F-id>.md (the request each item's task starts from)
    tasks/<id>/status.md       frontmatter (stage, round, ...) + "## Log"
    tasks/<id>/*.md            spec, build, reviews, decision, notes
    worktrees/<id>/            git worktree of branch factory/<id>

The orchestrator calls this script instead of editing status files by hand, so
the dashboard always reads a consistent format.
"""
import argparse
import datetime as dt
import html
import http.server
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
POLICY_TEMPLATE = PLUGIN_ROOT / "skills" / "factory" / "templates" / "factory.md"
STAGES = ["spec", "build", "review", "approve", "merge", "needs_human",
          "pr_open", "merged", "rejected", "failed"]


def now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def repo_root():
    """Root of the main checkout, also when called from inside a worktree."""
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            check=True, capture_output=True, text=True).stdout.strip()
    except subprocess.CalledProcessError:
        sys.exit("factory: not inside a git repository")
    return Path(common).parent


def factory_dir():
    return repo_root() / ".factory"


def task_dir(task_id):
    d = factory_dir() / "tasks" / task_id
    if not d.is_dir():
        sys.exit(f"factory: no task {task_id}")
    return d


def read_front(path):
    """key: value frontmatter between --- lines; inline '# comments' dropped."""
    text = path.read_text() if path.exists() else ""
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    data = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.lstrip().startswith("#"):
                k, v = line.split(":", 1)
                data[k.strip()] = re.sub(r"\s+#.*$", "", v).strip()
    return data, text[m.end():] if m else text


def write_front(path, data, body):
    lines = "\n".join(f"{k}: {v}" for k, v in data.items())
    path.write_text(f"---\n{lines}\n---\n{body}")


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40].rstrip("-") or "task"


# ---------------------------------------------------------------- commands

def cmd_init(args):
    root = repo_root()
    fd = root / ".factory"
    (fd / "tasks").mkdir(parents=True, exist_ok=True)
    (fd / "worktrees").mkdir(exist_ok=True)
    backlog = fd / "backlog.md"
    if not backlog.exists():
        backlog.write_text("# Backlog\n\n")
    exclude = Path(subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"],
        check=True, capture_output=True, text=True, cwd=root).stdout.strip())
    exclude.parent.mkdir(parents=True, exist_ok=True)
    current = exclude.read_text() if exclude.exists() else ""
    if ".factory/" not in current.split():
        exclude.write_text(current + ("" if current.endswith("\n") or not current else "\n") + ".factory/\n")
    policy = root / ".claude" / "factory.md"
    created = False
    if not policy.exists():
        policy.parent.mkdir(exist_ok=True)
        shutil.copy(POLICY_TEMPLATE, policy)
        created = True
    print(json.dumps({"root": str(root), "policy": str(policy),
                      "policy_created": created, "state": str(fd)}))


def cmd_policy(args):
    policy = repo_root() / ".claude" / "factory.md"
    if not policy.exists():
        sys.exit("factory: no .claude/factory.md, run /factory init first")
    data, _ = read_front(policy)
    data["path"] = str(policy)
    print(json.dumps(data if not args.key else data.get(args.key, "")))


# skill name in the policy -> (plugin, skill folders under the plugin's skills/)
KNOWN_SKILLS = {
    "impeccable": ("impeccable", ["impeccable"]),
    "ponytail": ("ponytail", ["ponytail", "ponytail-review"]),
}


def cmd_skills(args):
    """Resolve the policy's `skills:` to the installed skill folders agents should read."""
    root = repo_root()
    data, _ = read_front(root / ".claude" / "factory.md")
    wanted = [x.strip() for x in data.get("skills", "").split(",") if x.strip()]
    if not wanted:
        print(json.dumps({}))
        return
    try:
        out = subprocess.run(["claude", "plugin", "list", "--json"], cwd=root,
                             capture_output=True, text=True, timeout=60).stdout
        listed = json.loads(out)
        listed = listed if isinstance(listed, list) else listed.get("plugins", [])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        listed = []
    paths = {p["id"].split("@")[0]: Path(p["installPath"]) for p in listed
             if p.get("enabled") and p.get("installPath")
             and (p.get("scope") != "project" or p.get("projectPath") == str(root))}
    result, missing = {}, []
    for name in wanted:
        plugin, folders = KNOWN_SKILLS.get(name, (name, [name]))
        base = paths.get(plugin)
        found = [f for f in folders if base and (base / "skills" / f / "SKILL.md").exists()]
        if not found:
            missing.append(name)
        for f in found:
            result[f] = str(base / "skills" / f)
    if missing:
        result["missing"] = missing
    print(json.dumps(result))


def new_task(title, request):
    tasks = factory_dir() / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    base = f"{dt.date.today():%Y%m%d}-{slugify(title)}"
    task_id, n = base, 2
    while (tasks / task_id).exists():
        task_id, n = f"{base}-{n}", n + 1
    d = tasks / task_id
    d.mkdir()
    (d / "request.md").write_text(request.strip() + "\n")
    write_front(d / "status.md", {
        "id": task_id, "title": title.replace("\n", " ")[:80], "stage": "spec",
        "round": 0, "branch": f"factory/{task_id}", "decision": "",
        "created": now(), "updated": now()}, f"## Log\n- {now()} created\n")
    return task_id


def cmd_new(args):
    print(new_task(args.title, args.request or args.title))


def cmd_set(args):
    path = task_dir(args.id) / "status.md"
    data, body = read_front(path)
    for kv in args.pairs:
        if "=" not in kv:
            sys.exit(f"factory: expected key=value, got {kv}")
        k, v = kv.split("=", 1)
        if k == "stage" and v not in STAGES:
            sys.exit(f"factory: unknown stage {v}; one of {', '.join(STAGES)}")
        data[k] = v.replace("\n", " ")
    data["updated"] = now()
    write_front(path, data, body)


def cmd_log(args):
    path = task_dir(args.id) / "status.md"
    data, body = read_front(path)
    data["updated"] = now()
    write_front(path, data, body.rstrip("\n") + f"\n- {now()} {args.message}\n")


def all_tasks():
    tasks = factory_dir() / "tasks"
    out = []
    for d in sorted(tasks.iterdir()) if tasks.is_dir() else []:
        if (d / "status.md").exists():
            data, body = read_front(d / "status.md")
            data["log"] = [l[2:] for l in body.splitlines() if l.startswith("- ")][-8:]
            data["files"] = sorted(p.name for p in d.glob("*.md") if p.name != "status.md")
            out.append(data)
    return out


def cmd_list(args):
    rows = all_tasks()
    if args.json:
        print(json.dumps(rows, indent=1))
        return
    for t in rows:
        print(f"{t.get('id',''):45} {t.get('stage',''):12} r{t.get('round','0')}  {t.get('title','')}")
    if not rows:
        print("no tasks")


ITEM_RE = re.compile(r"^- \[(?P<mark>[ ~x-])\] (?:(?P<id>[FM]\d+) )?(?P<text>.*?)(?: -> (?P<task>\S+))?$")


def read_backlog():
    path = factory_dir() / "backlog.md"
    return path, (path.read_text() if path.exists() else "# Backlog\n\n").splitlines()


def parse_item(line):
    """'- [ ] F03 Title (deps: F01, F02) [ui] -> task' as a dict, or None."""
    m = ITEM_RE.match(line)
    if not m:
        return None
    d = m.groupdict()
    deps = re.search(r"\(deps: ([^)]*)\)", d["text"])
    d["deps"] = [x.strip() for x in deps.group(1).split(",") if x.strip()] if deps else []
    d["title"] = re.sub(r"\s*(\((deps|dropped):[^)]*\)|\[ui\])", "", d["text"]).strip()
    return d


def next_free_id(lines, prefix):
    """F ids come from the analyst's plan, M ids from items added by hand."""
    nums = [int(i["id"][1:]) for l in lines
            if (i := parse_item(l)) and i["id"] and i["id"][0] == prefix]
    return f"{prefix}{max(nums, default=0) + 1:02d}"


def cmd_backlog_add(args):
    path, lines = read_backlog()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines.append(f"- [ ] {next_free_id(lines, 'M')} {args.text.strip()}")
    path.write_text("\n".join(lines) + "\n")
    print(lines[-1])


def cmd_next(args):
    """Take the first open item whose deps are all done: create its task, mark it taken."""
    path, lines = read_backlog()
    items = {i["id"]: i for l in lines if (i := parse_item(l)) and i["id"]}
    blocked = []
    for n, line in enumerate(lines):
        item = parse_item(line)
        if not item or item["mark"] != " ":
            continue
        waiting = [d for d in item["deps"] if items.get(d, {}).get("mark") != "x"]
        if waiting:
            blocked.append(f"{item['id']} waits on {', '.join(waiting)}")
            continue
        card = factory_dir() / "plan" / "items" / f"{item['id']}.md"
        request = card.read_text() if item["id"] and card.exists() else item["title"]
        label = f"{item['id']} {item['title']}" if item["id"] else item["title"]
        task_id = new_task(label[:60], request)
        lines[n] = f"{line} -> {task_id}".replace("- [ ]", "- [~]", 1)
        path.write_text("\n".join(lines) + "\n")
        print(json.dumps({"id": task_id, "item": item["id"], "title": item["title"]}))
        return
    print(json.dumps({"blocked": blocked}))


def cmd_backlog_mark(args):
    """Close the backlog item a task came from: x = done, - = dropped."""
    path, lines = read_backlog()
    out = []
    for line in lines:
        item = parse_item(line)
        if item and item["task"] == args.id:
            line = line.replace(f"- [{item['mark']}]", f"- [{args.mark}]", 1)
        out.append(line)
    path.write_text("\n".join(out) + "\n")


def cmd_plan_apply(args):
    """Merge plan/proposed-backlog.md into backlog.md; taken or done items never change."""
    proposed = factory_dir() / "plan" / "proposed-backlog.md"
    if not proposed.exists():
        sys.exit("factory: no plan/proposed-backlog.md")
    path, lines = read_backlog()
    current = {i["id"]: l for l in lines if (i := parse_item(l)) and i["id"]}
    out, seen, counts = ["# Backlog", ""], set(), {"kept": 0, "set": 0, "dropped": 0}
    for line in proposed.read_text().splitlines():
        item = parse_item(line)
        if not item or not item["id"]:
            continue
        seen.add(item["id"])
        old = current.get(item["id"])
        if old and parse_item(old)["mark"] in "~x":
            out.append(old); counts["kept"] += 1
        else:
            out.append(line); counts["dropped" if item["mark"] == "-" else "set"] += 1
    # items the proposal forgot, and manual lines without an ID, are kept as they were
    out += [l for l in lines if (i := parse_item(l)) and (not i["id"] or i["id"] not in seen)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n")
    print(json.dumps(counts))


# ---------------------------------------------------------------- dashboard

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Software Factory</title><style>
:root{--bg:#f6f6f4;--card:#fff;--fg:#1d1d1b;--mute:#6b6b66;--line:#e2e2dc;
--spec:#3b6fd8;--build:#2f9a5b;--review:#c08a12;--approve:#d0632a;--human:#c43d3d;--done:#5b5b57}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#20201e;--fg:#ececea;--mute:#9a9a94;--line:#33332f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}
header{display:flex;gap:12px;align-items:baseline;padding:16px;border-bottom:1px solid var(--line)}
h1{font-size:17px;margin:0}header span{color:var(--mute);font-size:12px}
.board{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;padding:16px}
.col h2{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);margin:0 0 8px;display:flex;justify-content:space-between}
.card{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--c,var(--done));border-radius:8px;padding:10px;margin-bottom:8px;cursor:pointer}
.card b{display:block;font-weight:600;margin-bottom:4px}.card small{color:var(--mute)}
.pill{display:inline-block;font-size:11px;padding:0 6px;border-radius:9px;border:1px solid var(--line);margin:4px 4px 0 0}
.pass{color:var(--build)}.changes{color:var(--human)}
#detail{padding:0 16px 32px}#detail h3{margin:16px 0 8px}
.tabs button{font:inherit;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:4px 10px;margin:0 6px 6px 0;cursor:pointer}
.tabs button.on{border-color:var(--fg)}
pre{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:60vh;overflow:auto}
.empty{color:var(--mute);font-size:12px}
</style></head><body>
<header><h1>Software Factory</h1><span id="root"></span><span id="ts"></span></header>
<div class="board" id="board"></div><div id="detail"></div>
<script>
const COLS=[["Backlog",["backlog"],"--done"],["Spec",["spec"],"--spec"],["Build",["build"],"--build"],
["Review",["review"],"--review"],["Approve",["approve","merge"],"--approve"],["Needs human",["needs_human"],"--human"],
["Done",["merged","pr_open"],"--done"],["Stopped",["rejected","failed"],"--done"]];
let open=null,tab=null;const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
async function load(){const r=await fetch("api/state");const s=await r.json();
document.getElementById("root").textContent=s.root;document.getElementById("ts").textContent="updated "+new Date().toLocaleTimeString();
const b=document.getElementById("board");b.innerHTML="";
for(const [name,stages,color] of COLS){const items=stages[0]=="backlog"?s.backlog.map(t=>({title:t,stage:"backlog"})):s.tasks.filter(t=>stages.includes(t.stage));
const col=document.createElement("div");col.className="col";col.innerHTML=`<h2>${name}<span>${items.length}</span></h2>`;
if(!items.length)col.innerHTML+=`<div class="empty">—</div>`;
for(const t of items){const c=document.createElement("div");c.className="card";c.style.setProperty("--c",`var(${color})`);
const rv=Object.keys(t).filter(k=>k.startsWith("review_")).map(k=>`<span class="pill ${esc(t[k])}">${esc(k.slice(7))}: ${esc(t[k])}</span>`).join("");
c.innerHTML=`<b>${esc(t.title)}</b>`+(t.id?`<small>${esc(t.id)} · round ${esc(t.round)}${t.decision?" · "+esc(t.decision):""}</small><div>${rv}</div>`:"");
if(t.id)c.onclick=()=>{open=t.id;tab=null;show(s)};col.appendChild(c)}b.appendChild(col)}
if(open)show(s)}
async function show(s){const t=s.tasks.find(x=>x.id==open);if(!t)return;tab=tab||t.files.at(-1)||null;
const d=document.getElementById("detail");let body="";
if(tab){const r=await fetch(`api/file?task=${encodeURIComponent(t.id)}&name=${encodeURIComponent(tab)}`);body=await r.text()}
d.innerHTML=`<h3>${esc(t.title)}</h3><div class="tabs">${t.files.map(f=>`<button class="${f==tab?"on":""}" data-f="${esc(f)}">${esc(f)}</button>`).join("")}</div>
<pre>${esc(body)}</pre><h3>Log</h3><pre>${esc(t.log.join("\\n"))}</pre>`;
d.querySelectorAll("button").forEach(x=>x.onclick=()=>{tab=x.dataset.f;show(s)})}
load();setInterval(load,3000);
</script></body></html>"""


# Paths that send a light-profile task back to the full review: dependencies, schema,
# infrastructure, secrets, and code whose path names a sensitive area.
SENSITIVE = [
    (r"(^|/)(package\.json|package-lock\.json|yarn\.lock|pnpm-lock\.yaml|bun\.lockb?|requirements[^/]*\.txt"
     r"|pyproject\.toml|poetry\.lock|uv\.lock|Pipfile(\.lock)?|Cargo\.(toml|lock)|go\.(mod|sum)|Gemfile(\.lock)?"
     r"|composer\.(json|lock)|pubspec\.(yaml|lock)|Podfile(\.lock)?)$", "dependencies"),
    (r"(^|/)(migrations?|supabase|prisma|schema)(/|\.)|\.sql$", "database"),
    (r"(^|/)(\.github|\.gitlab-ci\.yml|\.circleci|Dockerfile|docker-compose[^/]*|terraform|infra|deploy)"
     r"|(^|/)(wrangler\.toml|vercel\.json|netlify\.toml|_headers|_redirects|app\.json|eas\.json)$", "infrastructure"),
    (r"(^|/)\.env|secret|credential|\.pem$|\.key$", "secrets"),
    (r"auth|login|logout|session|password|token|permission|role|admin|payment|billing|checkout"
     r"|subscription|stripe|delete-?account", "sensitive code"),
]


def cmd_light_check(args):
    """Diff size and sensitive paths of a task branch, to keep or leave the light review."""
    front, _ = read_front(task_dir(args.id) / "status.md")
    policy, _ = read_front(repo_root() / ".claude" / "factory.md")
    base, branch = front.get("base") or policy.get("base_branch", "main"), front["branch"]
    out = subprocess.run(["git", "-C", str(repo_root()), "diff", "--numstat", f"{base}...{branch}"],
                         check=True, capture_output=True, text=True).stdout
    lines, files, sensitive = 0, 0, []
    for row in out.splitlines():
        added, removed, path = row.split("\t", 2)
        files += 1
        lines += (int(added) if added.isdigit() else 0) + (int(removed) if removed.isdigit() else 0)
        for pattern, reason in SENSITIVE:
            if re.search(pattern, path, re.I):
                sensitive.append(f"{path}: {reason}")
                break
    limit = int(policy.get("max_auto_merge_lines") or 400)
    print(json.dumps({"light": not sensitive and lines <= limit, "lines": lines, "limit": limit,
                      "files": files, "sensitive": sensitive}))


def cmd_dashboard(args):
    root = repo_root()
    tasks_dir = root / ".factory" / "tasks"

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, body, ctype, code=200):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            from urllib.parse import urlparse, parse_qs
            u = urlparse(self.path)
            if u.path == "/":
                return self.send(PAGE, "text/html")
            if u.path == "/api/state":
                _, lines = read_backlog()
                backlog = [m.group(1) for l in lines if (m := re.match(r"^- \[ \] (.+)$", l))]
                return self.send(json.dumps({"root": str(root), "tasks": all_tasks(),
                                             "backlog": backlog}), "application/json")
            if u.path == "/api/file":
                q = parse_qs(u.query)
                task, name = q.get("task", [""])[0], q.get("name", [""])[0]
                d = tasks_dir / task
                # only plain .md files that exist directly in a task folder
                if (re.fullmatch(r"[\w.-]+", task) and re.fullmatch(r"[\w.-]+\.md", name)
                        and (d / name).is_file()):
                    return self.send((d / name).read_text(), "text/plain")
                return self.send("not found", "text/plain", 404)
            self.send("not found", "text/plain", 404)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"factory dashboard: http://127.0.0.1:{args.port}  ({root})", flush=True)
    srv.serve_forever()


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    s = sub.add_parser("policy"); s.add_argument("key", nargs="?"); s.set_defaults(fn=cmd_policy)
    sub.add_parser("skills").set_defaults(fn=cmd_skills)
    s = sub.add_parser("new"); s.add_argument("title"); s.add_argument("--request"); s.set_defaults(fn=cmd_new)
    s = sub.add_parser("set"); s.add_argument("id"); s.add_argument("pairs", nargs="+"); s.set_defaults(fn=cmd_set)
    s = sub.add_parser("log"); s.add_argument("id"); s.add_argument("message"); s.set_defaults(fn=cmd_log)
    s = sub.add_parser("list"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_list)
    s = sub.add_parser("backlog-add"); s.add_argument("text"); s.set_defaults(fn=cmd_backlog_add)
    sub.add_parser("next").set_defaults(fn=cmd_next)
    s = sub.add_parser("backlog-mark"); s.add_argument("id"); s.add_argument("mark", choices=["x", "-"]); s.set_defaults(fn=cmd_backlog_mark)
    sub.add_parser("plan-apply").set_defaults(fn=cmd_plan_apply)
    s = sub.add_parser("light-check"); s.add_argument("id"); s.set_defaults(fn=cmd_light_check)
    s = sub.add_parser("dashboard"); s.add_argument("--port", type=int, default=8765); s.set_defaults(fn=cmd_dashboard)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
