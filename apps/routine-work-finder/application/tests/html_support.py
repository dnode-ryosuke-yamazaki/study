"""レポートのHTMLを構造で確かめるための読み取りと、埋め込んだ JavaScript を node で動かす補助。

部分一致だけで済ませないよう、HTML は要素の木に組み立て、タグの対応が崩れていれば例外にする。
"""

import json
import os
import shutil
import subprocess
import tempfile
from html.parser import HTMLParser

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
NODE = shutil.which("node")


class Element:
    def __init__(self, tag, attrs, parent):
        self.tag = tag
        self.attrs = dict(attrs)
        self.parent = parent
        self.children = []

    def iter(self):
        yield self
        for child in self.children:
            if isinstance(child, Element):
                yield from child.iter()

    def find_all(self, tag=None, **attrs):
        return [element for element in self.iter() if (tag is None or element.tag == tag)
                and all(element.attrs.get(key.rstrip("_")) == value for key, value in attrs.items())]

    def find(self, tag=None, **attrs):
        found = self.find_all(tag, **attrs)
        return found[0] if found else None

    def by_id(self, element_id):
        return self.find(id=element_id)

    def classes(self):
        return (self.attrs.get("class") or "").split()

    def has_class(self, name):
        return name in self.classes()

    def with_class(self, name):
        return [element for element in self.iter() if element.has_class(name)]

    def text(self):
        parts = []
        for child in self.children:
            parts.append(child.text() if isinstance(child, Element) else child)
        return "".join(parts)

    def ancestors(self):
        node = self.parent
        while node is not None:
            yield node
            node = node.parent


class UnbalancedHtml(Exception):
    pass


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("#root", {}, None)
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        element = Element(tag, attrs, self.current)
        self.current.children.append(element)
        if tag not in VOID_TAGS:
            self.current = element

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Element(tag, attrs, self.current))

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if self.current.tag != tag:
            raise UnbalancedHtml(f"</{tag}> が <{self.current.tag}> を閉じようとしています")
        self.current = self.current.parent

    def handle_data(self, data):
        self.current.children.append(data)


def parse(html):
    """タグの対応を確かめながら要素の木にする。閉じていない要素があれば例外"""
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    if builder.current is not builder.root:
        raise UnbalancedHtml(f"<{builder.current.tag}> が閉じていません")
    return builder.root


def scripts(root):
    return [element.text() for element in root.find_all("script")]


def node_check(script_text):
    """node --check で構文を確かめ、(通ったか, エラーの出力) を返す"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as file:
        file.write(script_text)
        path = file.name
    try:
        proc = subprocess.run([NODE, "--check", path], capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(path)
    return proc.returncode == 0, proc.stderr


# node で動かすための、ブラウザの部品の偽物。document.execCommand とクリップボードの結果を切り替えられる
FAKE_BROWSER = r"""
var __elements = {};
var __created = [];
var __clipboardText = null;
function __element(id) {
  if (!__elements[id]) {
    __elements[id] = { id: id, hidden: true, value: "", textContent: "", className: "", disabled: true, style: {},
      focused: false, selected: false, attributes: {}, listeners: {},
      focus: function () { this.focused = true; }, select: function () { this.selected = true; },
      setSelectionRange: function () {}, setAttribute: function (k, v) { this.attributes[k] = v; },
      addEventListener: function (name, fn) { this.listeners[name] = fn; } };
  }
  return __elements[id];
}
globalThis.document = {
  body: { appendChild: function (el) { el.attached = true; }, removeChild: function (el) { el.attached = false; } },
  createElement: function (tag) { var el = __element("__created" + __created.length); el.tag = tag; __created.push(el); return el; },
  getElementById: __element,
  querySelectorAll: function () { return []; },
  execCommand: function (name) {
    if (__EXEC === "throw") { throw new Error("blocked"); }
    var last = __created[__created.length - 1];
    if (__EXEC === true && last && last.attached && last.selected) { __clipboardText = last.value; return true; }
    return false;
  }
};
Object.defineProperty(globalThis, "navigator", { configurable: true, writable: true, value:
  __CLIPBOARD === "none" ? {} : { clipboard: { writeText: function (text) {
    if (__CLIPBOARD === "ok") { __clipboardText = text; return Promise.resolve(); }
    return Promise.reject(new Error("denied"));
  } } } });
"""


def run_node(script_text, before, after):
    """偽物の部品(before で __EXEC・__CLIPBOARD を決める)の上で script を読み込み、after を実行して最後に出した JSON を返す"""
    program = before + FAKE_BROWSER + script_text + "\n" + after
    proc = subprocess.run([NODE, "-"], input=program, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError(f"node が失敗しました: {proc.stderr}")
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    return json.loads(lines[-1])
