"""Chunk Java source into method/class units for exemplar capture.

A CodeChunk is the atom the capture pipeline stores as an Exemplar: a named
span of code with plausible line bounds. We prefer tree-sitter when it is
installed, but it is an optional dependency (see the ban in the task contract),
so we fall back to a brace-and-signature heuristic. Parsing NEVER raises; a bad
parse degrades to a coarser chunk (or none) rather than an exception.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class CodeChunk:
    """A named slice of source. `kind` is method | class | other."""

    name: str
    kind: str
    start_line: int
    end_line: int
    code: str


def has_tree_sitter() -> bool:
    """True if both tree_sitter and a Java grammar are importable."""
    try:
        import tree_sitter  # noqa: F401
        import tree_sitter_java  # noqa: F401
    except Exception:
        return False
    return True


# --- signature detection for the fallback -----------------------------------
# Matches a method signature line: optional modifiers/annotations, a return
# type or `void`, the method name, a parenthesised parameter list, then `{`.
# Constructors (no return type) are also caught by the leading-name branch.
_METHOD_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|static|final|abstract|synchronized|"
    r"native|default|strictfp)\s+)*"
    r"(?:<[^>]+>\s*)?"  # generic type params
    r"(?:[\w.<>\[\],\s?&]+\s+)?"  # return type (absent for constructors)
    r"(\w+)\s*\([^;{]*\)\s*"  # name + params
    r"(?:throws\s+[\w.,\s]+)?\s*\{",  # optional throws, opening brace
)
_CLASS_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|static|final|abstract|sealed)\s+)*"
    r"(?:class|interface|enum|record)\s+(\w+)"
)
# Keywords that look like method signatures but are control flow, not methods.
_CONTROL = {"if", "for", "while", "switch", "catch", "synchronized", "try"}


def parse_java(source: str) -> list[CodeChunk]:
    """Parse Java source into CodeChunks, preferring methods.

    Tries tree-sitter first; on any failure (missing grammar, parse error)
    uses the heuristic fallback. Never raises.
    """
    if has_tree_sitter():
        try:
            return _parse_tree_sitter(source)
        except Exception:
            pass  # fall through to the heuristic
    return _parse_heuristic(source)


def _parse_tree_sitter(source: str) -> list[CodeChunk]:
    """Extract methods/classes via tree-sitter. Raises on any problem so the
    caller can fall back."""
    import tree_sitter_java
    from tree_sitter import Language, Node, Parser

    parser = Parser(Language(tree_sitter_java.language()))
    tree = parser.parse(source.encode("utf-8"))
    data = source.encode("utf-8")
    chunks: list[CodeChunk] = []

    def name_of(node: Node) -> str:
        ident = node.child_by_field_name("name")
        return data[ident.start_byte : ident.end_byte].decode("utf-8") if ident else "anon"

    def walk(node: Node) -> None:
        if node.type in ("method_declaration", "constructor_declaration"):
            kind = "method"
        elif node.type in ("class_declaration", "interface_declaration", "enum_declaration", "record_declaration"):
            kind = "class"
        else:
            kind = ""
        if kind:
            code = data[node.start_byte : node.end_byte].decode("utf-8")
            chunks.append(
                CodeChunk(
                    name=name_of(node),
                    kind=kind,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    code=code,
                )
            )
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    return _prefer_methods(chunks)


def _parse_heuristic(source: str) -> list[CodeChunk]:
    """Brace-matching fallback: find method and class bodies by signature +
    balanced braces. Line numbers are 1-based and inclusive."""
    lines = source.splitlines()
    chunks: list[CodeChunk] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        m_method = _METHOD_RE.match(line)
        m_class = _CLASS_RE.match(line)
        # Skip control-flow blocks that superficially match the method regex.
        if m_method and m_method.group(1) not in _CONTROL:
            end = _match_braces(lines, i)
            code = "\n".join(lines[i : end + 1])
            chunks.append(CodeChunk(m_method.group(1), "method", i + 1, end + 1, code))
            i = end + 1
            continue
        if m_class:
            end = _match_braces(lines, i)
            code = "\n".join(lines[i : end + 1])
            chunks.append(CodeChunk(m_class.group(1), "class", i + 1, end + 1, code))
            # Descend into the class body to pull out its methods.
            inner = _parse_heuristic("\n".join(lines[i + 1 : end]))
            for c in inner:
                chunks.append(
                    CodeChunk(c.name, c.kind, c.start_line + i + 1, c.end_line + i + 1, c.code)
                )
            i = end + 1
            continue
        i += 1

    return _prefer_methods(chunks)


def _match_braces(lines: list[str], start: int) -> int:
    """Return the index of the line closing the brace opened at/after `start`.

    Counts `{`/`}` from the first `{` on the start line onward, ignoring braces
    inside `"..."`, `'.'`, and `//` comments (best-effort, not a full lexer).
    Falls back to end-of-file if the braces never balance."""
    depth = 0
    seen = False
    for idx in range(start, len(lines)):
        depth += _brace_delta(lines[idx])
        if _brace_delta(lines[idx]) != 0 or "{" in lines[idx]:
            seen = seen or "{" in lines[idx]
        if seen and depth <= 0:
            return idx
    return len(lines) - 1


def _brace_delta(line: str) -> int:
    """Net `{` minus `}` on a line, skipping strings/chars/line comments."""
    depth = 0
    in_str: str | None = None
    j = 0
    while j < len(line):
        ch = line[j]
        if in_str:
            if ch == "\\":
                j += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in ('"', "'"):
            in_str = ch
        elif ch == "/" and j + 1 < len(line) and line[j + 1] == "/":
            break
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        j += 1
    return depth


def _prefer_methods(chunks: list[CodeChunk]) -> list[CodeChunk]:
    """If any methods were found, drop the enclosing class chunks; otherwise
    keep class-level chunks so we always return something usable."""
    methods = [c for c in chunks if c.kind == "method"]
    if methods:
        return methods
    return chunks


def chunk_java_file(path: str) -> list[CodeChunk]:
    """Read a Java file (utf-8, errors ignored) and chunk it.

    Prefers method-level chunks; falls back to class-level when a file has no
    parseable methods. Returns [] for an unreadable or empty file.
    """
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            source = fh.read()
    except OSError:
        return []
    return parse_java(source)
