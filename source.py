"""A position-preserving view of VAIL source with strings and comments blanked.

Every static check in this harness needs the same thing first: to look at CODE
without tripping over the contents of a string or a comment. Getting that wrong
is not theoretical. Two separate passes over this codebase corrupted live schema
because a matcher ran across a quote it should not have crossed:

  * A vocabulary scrub matched string literals before stripping comments. A `//`
    comment containing an odd number of double quotes left the matcher paired
    against the wrong quote, so it swallowed the code between two unrelated
    strings. `clinicalUse` became `operationalUse`, which is a column rename,
    and the type then rejected every row.

  * A find-and-replace on the token "VEN" hit INVENTORY. `AGT-INVENTORY-POLICY`
    became `AGT-INcriticalityTORY-POLICY` inside a string literal, where the
    text is an identifier rather than prose, and the agent stopped dispatching.

blank() returns a string of the SAME LENGTH as the input, with every string
literal and comment replaced by spaces. Offsets, line numbers and column numbers
all stay valid, so a rule can report against the original text while matching
only against code.
"""


def blank(text):
    """Same length, with string and comment content replaced by spaces.

    Quotes and comment markers themselves are blanked too, so a rule cannot
    accidentally match a delimiter. Newlines are preserved so line numbers of
    later content do not shift.
    """
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if c == "/" and nxt == "/":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue

        if c == "/" and nxt == "*":
            out.append("  ")
            i += 2
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            if i < n:
                out.append("  ")
                i += 2
            continue

        if c in ('"', "'", "`"):
            quote = c
            out.append(" ")
            i += 1
            while i < n:
                if text[i] == "\\" and i + 1 < n:
                    out.append("  ")
                    i += 2
                    continue
                if text[i] == quote:
                    out.append(" ")
                    i += 1
                    break
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            continue

        out.append(c)
        i += 1

    blanked = "".join(out)
    assert len(blanked) == len(text), "blank() changed length; offsets would lie"
    return blanked


def line_of(text, offset):
    """1-indexed line number for a character offset."""
    return text.count("\n", 0, offset) + 1


def line_text(text, offset):
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    return text[start:end if end != -1 else len(text)].strip()
