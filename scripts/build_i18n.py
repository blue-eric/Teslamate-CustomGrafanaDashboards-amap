#!/usr/bin/env python3
"""Generate translated copies of the dashboards from a translation table.

The English dashboards stay the single source of truth: dashboards/ (kept in
sync with the upstream project) and teslamate/source/ (TeslaMate's own
dashboards, see scripts/sync_teslamate.sh). This script reads them, replaces
the user-visible texts using i18n/<lang>.json and writes the result to
dashboards-<lang>/ and teslamate/<code>/. TeslaMate's dashboards also get
their maps switched to AMap (scripts/teslamate_amap.py), in English as well
(teslamate/en/).

Column names returned by the SQL are translated with display-name overrides,
so queries and field references keep working. The only SQL changes are the
display-only snippets listed by hand in i18n/<lang>.sql.json (for example the
text 'Other' or the to_char() month format); --update never adds to that file.
Dashboard variables can get other choices or defaults for the language (for
example the currency) in i18n/<lang>.variables.json.
Column names that look like identifiers ("speed") are only translated when
they are added to the table by hand.

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import teslamate_amap  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESLAMATE = os.path.join(ROOT, "teslamate")

# Dashboard sets built from the same translation tables:
# - this repository's custom dashboards: own uids (suffix) and folder tag, so
#   both languages can be installed side by side;
# - TeslaMate's own dashboards (teslamate/source, see scripts/sync_teslamate.sh):
#   maps switched to AMap and the uids kept, so they replace the dashboards of
#   the teslamate/grafana image and every link to them keeps working. The
#   English AMap version is written to teslamate/en as well.
SETS = [
    {"src": os.path.join(ROOT, "dashboards"), "out": "{out}", "uid_suffix": True, "retag": True},
    {"src": os.path.join(TESLAMATE, "source"), "out": os.path.join(TESLAMATE, "{code}", "dashboards"),
     "amap": True, "en": os.path.join(TESLAMATE, "en", "dashboards")},
    {"src": os.path.join(TESLAMATE, "source", "internal"), "out": os.path.join(TESLAMATE, "{code}", "dashboards_internal"),
     "amap": True, "en": os.path.join(TESLAMATE, "en", "dashboards_internal")},
    {"src": os.path.join(TESLAMATE, "source", "reports"), "out": os.path.join(TESLAMATE, "{code}", "dashboards_reports"),
     "amap": True, "en": os.path.join(TESLAMATE, "en", "dashboards_reports")},
]

# Per language: translation tables, output folder of the custom dashboards,
# their uid suffix and folder tag, and the folder name under teslamate/.
LANGS = {
    "zh-CN": {
        "table": os.path.join(ROOT, "i18n", "zh-CN.json"),
        "sql_table": os.path.join(ROOT, "i18n", "zh-CN.sql.json"),
        "values_table": os.path.join(ROOT, "i18n", "zh-CN.values.json"),
        "variables_table": os.path.join(ROOT, "i18n", "zh-CN.variables.json"),
        "out": os.path.join(ROOT, "dashboards-zh"),
        "code": "zh",
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
    def __init__(self, table, sql_table, values_table=None):
        self.table = table
        self.sql_table = sql_table
        self.values_table = values_table or {}
        self.seen = []  # every translatable text, in order of appearance
        self.sql_used = set()
        self.problems = []

    def __call__(self, text):
        if not translatable(text):
            return text
        if text not in self.seen:
            self.seen.append(text)
        return self._result(text)

    def optional(self, text):
        """Translate only if the table has an entry; never added by --update."""
        if not isinstance(text, str) or text not in self.table:
            return text
        if text not in self.seen:
            self.seen.append(text)
        return self._result(text)

    def _result(self, text):
        result = self.table.get(text) or ""
        if not result:
            return text
        if variable_names(result) != variable_names(text):
            self.problems.append(f"variables differ, kept English: {text!r} -> {result!r}")
            return text
        return result

    def sql(self, sql):
        """Replace display-only SQL snippets listed in i18n/<lang>.sql.json."""
        replaced = {}
        for old, new in self.sql_table.items():
            if old.startswith("_") or not new or old not in sql:
                continue
            self.sql_used.add(old)
            if variable_names(old) != variable_names(new):
                self.problems.append(f"variables differ, SQL kept: {old!r} -> {new!r}")
                continue
            sql = sql.replace(old, new)
            # A replaced text literal may be a series name that overrides match on.
            literal_old, literal_new = re.findall(r"'([^']*)'", old), re.findall(r"'([^']*)'", new)
            if len(literal_old) == 1 and len(literal_new) == 1:
                replaced[literal_old[0]] = literal_new[0]
        return sql, replaced


def iter_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from iter_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_strings(value)


def replace_strings(node, old, new):
    """Replace string values equal to old anywhere inside node."""
    items = node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else []
    for key, value in list(items):
        if value == old:
            node[key] = new
        else:
            replace_strings(value, old, new)


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


ALIAS_RE = re.compile(r'\bAS\s+(?:"([^"]+)"|([A-Za-z_][A-Za-z0-9_${}]*))', re.IGNORECASE)


def sql_aliases(panel):
    """Column names the panel's queries return (Postgres lowercases unquoted ones)."""
    names = []
    for target in panel.get("targets") or []:
        if target.get("hide"):
            continue
        for quoted, plain in ALIAS_RE.findall(str(target.get("rawSql", ""))):
            name = quoted or plain.lower()
            if name not in names:
                names.append(name)
    return names


def is_alias_in(name, sql):
    name = re.escape(name.lower())
    return re.search(rf'"{name}"|\bas\s+{name}(?![\w$])', sql) is not None


def name_matcher(name):
    """Override matcher for a column name; names with variables need a regex."""
    if not VAR_RE.search(name):
        return {"id": "byName", "options": name}
    parts = VAR_RE.split(name)
    return {"id": "byRegexp", "options": "/^" + ".+".join(re.escape(part) for part in parts) + "$/"}


def translate_panel(panel, t, sources=()):
    """sources: panels whose query results this panel reuses (-- Dashboard -- datasource)."""
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
    # matchers, table sorting), so they are renamed together. A name that is
    # also a column name in the panel's SQL might be matched as a raw column
    # name and is left as is.
    sql = "\n".join([panel_sql(panel)] + [panel_sql(source) for source in sources]).lower()
    aliases = sql_aliases(panel)
    for source in sources:
        aliases += [name for name in sql_aliases(source) if name not in aliases]
    renamed = {}

    # Raw database values shown as text (i18n/<lang>.values.json).
    for snippet, values in t.values_table.items():
        if snippet.startswith("_") or snippet.lower() not in sql:
            continue
        t.sql_used.add(snippet)
        options_ = {raw: {"index": i, "text": text} for i, (raw, text) in enumerate(values.items())}
        defaults.setdefault("mappings", []).append({"type": "value", "options": options_})
        field_config["defaults"] = defaults
        panel["fieldConfig"] = field_config

    # Display-only texts produced by the SQL itself (e.g. 'Other', month names).
    for target in panel.get("targets") or []:
        if isinstance(target.get("rawSql"), str):
            target["rawSql"], literals = t.sql(target["rawSql"])
            renamed.update(literals)

    def rename(name):
        if not translatable(name):
            return name
        new = t(name)
        if new != name and not is_alias_in(name, sql):
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
            elif prop.get("id") == "unit":
                prop["value"] = t.optional(prop.get("value"))
    if "unit" in defaults:
        defaults["unit"] = t.optional(defaults["unit"])
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

    # Column names coming straight from the SQL get a display name through an
    # override added after the existing ones, so the SQL and the existing
    # overrides keep using the original names. Readable names ("Power [kW]")
    # are collected automatically, others ("speed") only when in the table.
    if defaults.get("displayName"):
        return
    handled = set()
    regexes = []
    for override in overrides:
        matcher = override.get("matcher") or {}
        ids = {prop.get("id") for prop in override.get("properties") or []}
        if "displayName" not in ids:
            continue
        if matcher.get("id") == "byName":
            handled.add(matcher.get("options"))
        elif matcher.get("id") == "byRegexp":
            regexes.append(str(matcher.get("options", "")).strip("/"))
    for transformation in panel.get("transformations") or []:
        handled.update(((transformation.get("options") or {}).get("renameByName") or {}).keys())
    # Identifier-like names added to the table by hand may also be plain
    # columns without an alias ("SELECT battery_level ...").
    for name in t.table:
        if (re.fullmatch(r"[a-z_][a-z0-9_]*", name) and name not in aliases
                and re.search(rf"(?:\bselect|,)\s*(?:\w+\.)?{name}\s*(?:,|\bfrom\b)", sql)):
            aliases.append(name)
    # Table sorting and regex field selectors (e.g. reduceOptions.fields
    # "/^Added$/") refer to the display name: a plain "/^name$/" selector is
    # renamed along with the column, a column used in any other regex keeps
    # its original name.
    selectors = [value for value in iter_strings(options) if value.startswith("/")]

    def new_name(name):
        readable = re.search(r"[A-Z\s\[\(%#]", VAR_RE.sub("", name))
        return t(name) if readable and translatable(name) else t.optional(name)

    def regex_matches(selector, name):
        body = re.sub(r"^/|/[a-z]*$", "", selector)
        try:
            return re.search(body, VAR_RE.sub("x", name)) is not None
        except re.error:
            return True  # unknown pattern: assume it matches, keep the name

    # A regex selector such as "/Inside/" may select several columns. A column
    # whose new name the selector no longer matches is renamed only if the
    # selector can be translated with it (a plain word in the table whose
    # translation is part of the new name); otherwise it keeps its name.
    candidates = [name for name in aliases
                  if name not in handled and not any(re.search(pattern, VAR_RE.sub("x", name)) for pattern in regexes)]
    selector_new = {}
    blocked = set()
    for selector in selectors:
        lost = [name for name in candidates if selector != f"/^{name}$/" and regex_matches(selector, name)
                and new_name(name) != name and not regex_matches(selector, new_name(name))]
        if not lost:
            continue
        word = re.fullmatch(r"/([A-Za-z][A-Za-z ]*)/", selector)
        word_new = t.optional(word.group(1)) if word else None
        if word and word_new != word.group(1) and all(word_new in new_name(name) for name in lost):
            selector_new[selector] = "/" + re.escape(word_new) + "/"
        else:
            blocked.update(lost)
    added = []
    for name in candidates:
        if name in blocked:
            continue
        plain_selector = f"/^{name}$/"
        if any(name in selector and selector != plain_selector and selector not in selector_new for selector in selectors):
            continue
        new = new_name(name)
        if new == name:
            continue
        added.append({"matcher": name_matcher(name), "properties": [{"id": "displayName", "value": new}]})
        replace_strings(options, plain_selector, "/^" + re.escape(new) + "$/")
        for sort in options.get("sortBy") or []:
            if sort.get("displayName") == name:
                sort["displayName"] = new
    if added:
        for old_selector, new_selector in selector_new.items():
            replace_strings(options, old_selector, new_selector)
    if added:
        field_config.setdefault("overrides", []).extend(added)
        panel["fieldConfig"] = field_config


def translate_variable(variable, t):
    for key in ("label", "description"):
        if key in variable:
            variable[key] = t(variable[key])
    if not variable.get("label") and variable.get("hide") in (None, 0) and translatable(variable.get("name")):
        label = t(variable["name"])  # Grafana shows the name when there is no label
        if label != variable["name"]:
            variable["label"] = label
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


def override_variables(dashboard, overrides, problems):
    """Replace the choices ("query") and/or the default of the listed variables."""
    variables = {v.get("name"): v for v in (dashboard.get("templating") or {}).get("list") or []}
    for name, override in overrides.items():
        variable = variables.get(name)
        if variable is None:
            problems.append(f"variable no longer found: {dashboard.get('uid')} ${name}")
            continue
        if "query" in override:
            variable["query"] = override["query"]
        if variable.get("type") == "custom":
            options = []
            for item in re.split(r"(?<!\\),", variable.get("query", "")):
                item = item.strip()
                if item:
                    text, value = (part.strip() for part in item.split(" : ", 1)) if " : " in item else (item, item)
                    options.append({"selected": False, "text": text, "value": value})
        else:  # textbox and similar: the query is the default value
            if "default" in override:
                variable["query"] = override["default"]
            options = [{"selected": False, "text": variable.get("query", ""), "value": variable.get("query", "")}]
        default = override.get("default", (variable.get("current") or {}).get("value"))
        selected = next((o for o in options if o["value"] == default), None)
        if selected is None:
            problems.append(f"default {default!r} is not a choice of {dashboard.get('uid')} ${name}")
            selected = options[0]
        selected["selected"] = True
        variable["options"] = options
        variable["current"] = {"text": selected["text"], "value": selected["value"]}


def translate_dashboard(dashboard, t, lang, custom_uids):
    for key in ("title", "description"):
        if key in dashboard:
            dashboard[key] = t(dashboard[key])
    translate_links(dashboard.get("links"), t)
    for annotation in (dashboard.get("annotations") or {}).get("list") or []:
        if annotation.get("builtIn"):
            continue
        if "name" in annotation:
            annotation["name"] = t(annotation["name"])
        for holder in (annotation, annotation.get("target") or {}):
            for key in ("rawQuery", "rawSql"):
                if isinstance(holder.get(key), str):
                    holder[key], _ = t.sql(holder[key])
    panels = list(iter_panels(dashboard.get("panels")))
    originals = {panel.get("id"): copy.deepcopy(panel) for panel in panels}
    for panel in panels:
        sources = [originals[target["panelId"]] for target in panel.get("targets") or []
                   if isinstance(target.get("panelId"), int) and target["panelId"] in originals]
        translate_panel(panel, t, sources)
    for variable in (dashboard.get("templating") or {}).get("list") or []:
        translate_variable(variable, t)

    if not lang.get("uid_suffix"):
        return  # TeslaMate's own dashboards keep their uids and tags
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
    sql_table = {}
    if os.path.exists(lang["sql_table"]):
        with open(lang["sql_table"], encoding="utf-8") as f:
            sql_table = json.load(f)
    values_table = {}
    if os.path.exists(lang["values_table"]):
        with open(lang["values_table"], encoding="utf-8") as f:
            values_table = json.load(f)
    t = Translator(table, sql_table, values_table)
    variables_table = {}
    if os.path.exists(lang.get("variables_table", "")):
        with open(lang["variables_table"], encoding="utf-8") as f:
            variables_table = json.load(f)

    # output path -> file content, for every set
    outputs = {}
    out_dirs = []
    dashboard_names = set()
    for spec in SETS:
        if not os.path.isdir(spec["src"]):
            continue
        out_dir = spec["out"].format(out=lang["out"], code=lang["code"])
        out_dirs.append(out_dir)
        dashboards = {}
        for path in sorted(glob.glob(os.path.join(spec["src"], "*.json"))):
            with open(path, encoding="utf-8") as f:
                dashboards[os.path.basename(path)] = json.load(f)
        dashboard_names.update(dashboards)
        custom_uids = [d["uid"] for d in dashboards.values()]
        set_lang = dict(lang) if spec.get("uid_suffix") else dict(lang, uid_suffix="", tag=None)
        if spec.get("en"):
            out_dirs.append(spec["en"])
        for name, dashboard in dashboards.items():
            if spec.get("amap"):
                teslamate_amap.amapify(dashboard, t.problems)
                if spec.get("en"):
                    outputs[os.path.join(spec["en"], name)] = dump(dashboard)
            translated = copy.deepcopy(dashboard)
            translate_dashboard(translated, t, set_lang, custom_uids)
            override_variables(translated, variables_table.get(name) or {}, t.problems)
            outputs[os.path.join(out_dir, name)] = dump(translated)

    missing = [text for text in t.seen if not table.get(text)]
    unused = [text for text in table if text not in t.seen]
    for name in variables_table:
        if not name.startswith("_") and name not in dashboard_names:
            t.problems.append(f"dashboard no longer found: {name} (i18n/{args.lang}.variables.json)")
    for old in list(sql_table) + list(values_table):
        if not old.startswith("_") and old not in t.sql_used:
            t.problems.append(f"SQL snippet no longer found in any dashboard: {old!r}")
    for problem in t.problems:
        print("WARNING:", problem)

    if args.check:
        stale = [path for path, content in outputs.items()
                 if not os.path.exists(path) or open(path, encoding="utf-8").read() != content]
        extra = [os.path.join(d, n) for d in out_dirs if os.path.isdir(d)
                 for n in os.listdir(d) if n.endswith(".json") and os.path.join(d, n) not in outputs]
        print(f"untranslated: {len(missing)}, unused: {len(unused)}, "
              f"out of date: {len(stale) + len(extra)}, warnings: {len(t.problems)}")
        for text in missing:
            print("  untranslated:", json.dumps(text, ensure_ascii=False)[:120])
        for path in stale + extra:
            print("  out of date:", os.path.relpath(path, ROOT))
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

    for out_dir in out_dirs:
        os.makedirs(out_dir, exist_ok=True)
        for name in os.listdir(out_dir):
            if name.endswith(".json") and os.path.join(out_dir, name) not in outputs:
                os.remove(os.path.join(out_dir, name))
    for path, content in outputs.items():
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    print(f"{len(outputs)} dashboards written; "
          f"{len(t.seen) - len(missing)}/{len(t.seen)} texts translated"
          + (f", {len(missing)} still in English (run with --update, then fill them in)" if missing else ""))


if __name__ == "__main__":
    main()
