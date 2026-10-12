#!/usr/bin/env python3
"""Generate translated copies of the dashboards from a translation table.

The English dashboards in dashboards/ stay the single source of truth (they are
kept in sync with the upstream project). This script reads them, replaces the
user-visible texts using i18n/<lang>.json and writes the result to
dashboards-<lang>/. SQL queries and field references are never touched.

Typical use after merging upstream changes:

    python3 scripts/build_i18n.py --update   # add new English texts to the table
    # fill in the entries whose value is still "" in i18n/zh-CN.json
    python3 scripts/build_i18n.py            # regenerate dashboards-zh/

Options:
    --update  add texts that are missing from the table (with an empty value)
    --prune   remove table entries that no dashboard uses any more
    --check   exit with status 1 if any text is untranslated (or the generated
              files are out of date), without writing anything
Untranslated texts fall back to English in the generated dashboards.
"""

import argparse
import copy
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "dashboards")

# Per language: translation table, output folder, uid suffix and folder tag.
LANGS = {
    "zh-CN": {
        "table": os.path.join(ROOT, "i18n", "zh-CN.json"),
        "out": os.path.join(ROOT, "dashboards-zh"),
        "uid_suffix": "-zh",
        "tag": "TeslamateCustomDashboardsZh",
    },
}

SRC_TAG = "TeslamateCustomDashboards"
VAR_RE = re.compile(r"\$\{[^}]+\}|\$[A-Za-z_][A-Za-z0-9_]*|\[\[[^\]]+\]\]")
LETTER_RE = re.compile(r"[A-Za-z]")


def variable_names(text):
    """Variables used in a text; ${name:format} counts as the same variable."""
    return sorted(re.sub(r"^\$\{|^\[\[|^\$|[:}\]].*$", "", token) for token in VAR_RE.findall(text))


def translatable(text):
    """Only texts that contain letters and are not just a variable."""
    if not isinstance(text, str) or not LETTER_RE.search(text):
        return False
    return VAR_RE.sub("", text).strip() != "" and LETTER_RE.search(VAR_RE.sub("", text))


class Translator:
    def __init__(self, table):
        self.table = table
        self.seen = []  # every translatable text, in order of appearance
        self.problems = []

    def __call__(self, text):
        if not translatable(text):
            return text
        if text not in self.seen:
            self.seen.append(text)
        result = self.table.get(text) or ""
        if not result:
            return text
        if variable_names(result) != variable_names(text):
            self.problems.append(f"variables differ, kept English: {text!r} -> {result!r}")
            return text
        return result


def iter_panels(panels):
    for panel in panels or []:
        yield panel
        yield from iter_panels(panel.get("panels"))


def translate_mappings(mappings, t):
    for mapping in mappings or []:
        if "text" in mapping:  # legacy mapping format
            mapping["text"] = t(mapping["text"])
        options = mapping.get("options") or {}
        if mapping.get("type") == "value":
            for option in options.values():
                if isinstance(option, dict) and "text" in option:
                    option["text"] = t(option["text"])
        elif isinstance(options.get("result"), dict) and "text" in options["result"]:
            options["result"]["text"] = t(options["result"]["text"])


def translate_links(links, t):
    for link in links or []:
        for key in ("title", "tooltip"):
            if key in link:
                link[key] = t(link[key])


def translate_field_config(config, t):
    """Texts inside fieldConfig.defaults or an override property list."""
    for key in ("noValue",):
        if key in config:
            config[key] = t(config[key])
    custom = config.get("custom") or {}
    if "axisLabel" in custom:
        custom["axisLabel"] = t(custom["axisLabel"])
    translate_mappings(config.get("mappings"), t)
    translate_links(config.get("links"), t)


def panel_sql(panel):
    return "\n".join(str(target.get("rawSql", "")) + str(target.get("query", ""))
                     for target in panel.get("targets") or [])


def translate_panel(panel, t):
    for key in ("title", "description"):
        if key in panel:
            panel[key] = t(panel[key])
    translate_links(panel.get("links"), t)
    options = panel.get("options") or {}
    if panel.get("type") == "text" and "content" in options:
        options["content"] = t(options["content"])

    field_config = panel.get("fieldConfig") or {}
    defaults = field_config.get("defaults") or {}
    overrides = field_config.get("overrides") or []
    translate_field_config(defaults, t)

    # Field display names may be referenced elsewhere in the panel (override
    # matchers, table sorting), so they are renamed together. A name that also
    # appears in the panel's SQL might be a raw column name and is left as is.
    sql = panel_sql(panel).lower()
    renamed = {}

    def rename(name):
        if not translatable(name) or f'"{name.lower()}"' in sql or f"as {name.lower()}" in sql:
            return name
        new = t(name)
        if new != name:
            renamed[name] = new
        return new

    if "displayName" in defaults:
        defaults["displayName"] = rename(defaults["displayName"])
    for override in overrides:
        for prop in override.get("properties") or []:
            if prop.get("id") == "displayName":
                prop["value"] = rename(prop.get("value"))
            elif prop.get("id") == "custom.axisLabel":
                prop["value"] = t(prop.get("value"))
            elif prop.get("id") == "noValue":
                prop["value"] = t(prop.get("value"))
            elif prop.get("id") == "mappings":
                translate_mappings(prop.get("value"), t)
            elif prop.get("id") == "links":
                translate_links(prop.get("value"), t)
    for transformation in panel.get("transformations") or []:
        if transformation.get("id") == "organize":
            names = (transformation.get("options") or {}).get("renameByName") or {}
            for key, value in names.items():
                names[key] = rename(value)

    for override in overrides:
        matcher = override.get("matcher") or {}
        if matcher.get("id") == "byName" and matcher.get("options") in renamed:
            matcher["options"] = renamed[matcher["options"]]
    for sort in options.get("sortBy") or []:
        if sort.get("displayName") in renamed:
            sort["displayName"] = renamed[sort["displayName"]]


def translate_variable(variable, t):
    for key in ("label", "description"):
        if key in variable:
            variable[key] = t(variable[key])
    if variable.get("type") != "custom":
        return
    # "a, b" or "text : value" items: translate the displayed text only.
    items = []
    texts = {}
    for item in re.split(r"(?<!\\),", variable.get("query", "")):
        item = item.strip()
        if not item:
            continue
        text, value = (part.strip() for part in item.split(" : ", 1)) if " : " in item else (item, item)
        new = t(text)
        if new != text:
            texts[value] = new
        items.append(f"{new} : {value}" if new != value else value)
    if texts:
        variable["query"] = ", ".join(items)
    for option in variable.get("options") or []:
        if option.get("value") in texts:
            option["text"] = texts[option["value"]]
    current = variable.get("current") or {}
    if isinstance(current.get("value"), str) and current["value"] in texts:
        current["text"] = texts[current["value"]]


def translate_dashboard(dashboard, t, lang, custom_uids):
    for key in ("title", "description"):
        if key in dashboard:
            dashboard[key] = t(dashboard[key])
    translate_links(dashboard.get("links"), t)
    for panel in iter_panels(dashboard.get("panels")):
        translate_panel(panel, t)
    for variable in (dashboard.get("templating") or {}).get("list") or []:
        translate_variable(variable, t)

    # Own uid, folder tag and links between the custom dashboards, so the
    # translated set can be installed next to the English one.
    dashboard["uid"] = dashboard["uid"] + lang["uid_suffix"]
    dashboard["tags"] = [lang["tag"] if tag == SRC_TAG else tag for tag in dashboard.get("tags") or []]
    for link in dashboard.get("links") or []:
        link["tags"] = [lang["tag"] if tag == SRC_TAG else tag for tag in link.get("tags") or []]
    uid_re = re.compile(r"\bd/(" + "|".join(map(re.escape, custom_uids)) + r")\b")

    def fix_urls(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, str) and key in ("url", "content"):
                    node[key] = uid_re.sub(lambda m: "d/" + m.group(1) + lang["uid_suffix"], value)
                else:
                    fix_urls(value)
        elif isinstance(node, list):
            for value in node:
                fix_urls(value)

    fix_urls(dashboard)


def dump(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lang", default="zh-CN", choices=sorted(LANGS))
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--prune", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    lang = LANGS[args.lang]

    table = {}
    if os.path.exists(lang["table"]):
        with open(lang["table"], encoding="utf-8") as f:
            table = json.load(f)
    t = Translator(table)

    sources = sorted(glob.glob(os.path.join(SRC_DIR, "*.json")))
    dashboards = {}
    for path in sources:
        with open(path, encoding="utf-8") as f:
            dashboards[os.path.basename(path)] = json.load(f)
    custom_uids = [d["uid"] for d in dashboards.values()]

    outputs = {}
    for name, dashboard in dashboards.items():
        translated = copy.deepcopy(dashboard)
        translate_dashboard(translated, t, lang, custom_uids)
        outputs[name] = dump(translated)

    missing = [text for text in t.seen if not table.get(text)]
    unused = [text for text in table if text not in t.seen]
    for problem in t.problems:
        print("WARNING:", problem)

    if args.check:
        stale = []
        for name, content in outputs.items():
            path = os.path.join(lang["out"], name)
            if not os.path.exists(path) or open(path, encoding="utf-8").read() != content:
                stale.append(name)
        extra = set(os.listdir(lang["out"])) - set(outputs) if os.path.isdir(lang["out"]) else set()
        print(f"untranslated: {len(missing)}, unused: {len(unused)}, "
              f"out of date: {len(stale) + len(extra)}, warnings: {len(t.problems)}")
        for text in missing:
            print("  untranslated:", json.dumps(text, ensure_ascii=False)[:120])
        for name in stale + sorted(extra):
            print("  out of date:", name)
        sys.exit(1 if missing or stale or extra or t.problems else 0)

    if args.update or args.prune:
        new_table = {}
        for text in t.seen:  # keep the order in which the texts appear
            if text in table or args.update:
                new_table[text] = table.get(text, "")
        if not args.prune:
            for text in unused:
                new_table[text] = table[text]
        os.makedirs(os.path.dirname(lang["table"]), exist_ok=True)
        with open(lang["table"], "w", encoding="utf-8") as f:
            f.write(dump(new_table))
        print(f"{lang['table']}: {len(missing)} new text(s) added" if args.update else "",
              f"{len(unused)} unused removed" if args.prune else "")

    os.makedirs(lang["out"], exist_ok=True)
    for name in os.listdir(lang["out"]):
        if name.endswith(".json") and name not in outputs:
            os.remove(os.path.join(lang["out"], name))
    for name, content in outputs.items():
        with open(os.path.join(lang["out"], name), "w", encoding="utf-8") as f:
            f.write(content)
    print(f"{len(outputs)} dashboards written to {lang['out']}; "
          f"{len(t.seen) - len(missing)}/{len(t.seen)} texts translated"
          + (f", {len(missing)} still in English (run with --update, then fill them in)" if missing else ""))


if __name__ == "__main__":
    main()
