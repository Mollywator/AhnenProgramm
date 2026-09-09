# The shape a tree is written in

`baum.json` is the whole of a family: the people, how they are joined, and what
is known about the tree itself. This file says what is in it, one section per
version, and **sections are added, never rewritten.**

That rule is the point of the file. A conversion may eventually be dropped once
no file that old can still exist; what version 1 looked like stays true for
ever, and it is what makes a backup from 2026 readable in 2036 even with no
program left that understands it. Somebody holding an old file and this document
can get the data out with a text editor.

`meta.format` says which version a file is in. A file with no such field is
version 1 — the field arrived with the machinery, so everything written before
it is by definition the shape that existed then. The program brings older files
forward on open, keeping a copy of the original first; see
[`tools/format.py`](../tools/format.py).

No real data appears in this document. Field names and types only.

---

## Version 1

The first shape, in use since the program's beginning and stamped with a number
since 07.09.2026.

### The file

```
{
  "meta":          { … }      about the tree itself
  "people":        [ … ]      one entry per person
  "marriages":     [ … ]      who is married to whom
  "source_titles": { … }      the sources, by key
  "checks":        [ … ]      what the parser could not reconcile
}
```

### `meta`

| Field | Type | What it is |
|---|---|---|
| `format` | int | the version of this shape. Absent means 1 |
| `title` | string | the tree's name, shown in the program and on the page |
| `count` | int | how many people. Written on save, from `people` |
| `photos` | int | how many portraits are actually in `fotos/` |
| `span` | string | the years the tree covers |
| `root` | int or null | whose diagram opens first — a person `id` |
| `source` | string | where the data came from |
| `source_author` | string | who gathered it. Appears in the page footer |
| `source_note` | string | a remark about the source |
| `gespeichert` | ISO date-time | when it was last written |
| `edited` | ISO date-time | when a person was last changed by hand |
| `edited_people` | int | how many people have been touched by hand |
| `umgewandelt` | object | present only after a conversion: `am`, `von`, `auf`, `schritte` |

`umgewandelt` is a **record, never a trigger.** It says what was done to this
file once, the options page shows it, and it stays for as long as the file does.
What must not happen is a reader treating it as a thing still to be done:
whether a conversion took place is known by the code that just performed one,
and by nothing else.

This is written down because it was got wrong. `store.load` used to decide
whether to write the tree back by reading this field — which it had itself
written the last time — so it wrote it back on every single open. `save` writes
the name list, the name list read the tree, and `save` therefore reached itself
about two hundred rounds deep, ending only when Python ran out of stack. Opening
a tree of two people took seven seconds, a save took six, and the twenty rolling
backups were replaced by twenty copies of the same second. See
`tools/test_umwandlung.py`, which holds the promise open.

### A person, in `people`

Every person carries every field. Ones that do not apply are `null`, or an empty
list where the field is a list — a person is never a short object.

| Field | Type | What it is |
|---|---|---|
| `id` | int | the number. The only thing telling two same-named people apart |
| `name` | string | the full name as shown. The editor writes it from `given`, `surname` and, behind a comma, `birth_name`, unless somebody typed a line of their own here |
| `given`, `surname` | string | the two halves, split by the parser |
| `birth_name` | string or null | the name before marriage |
| `call_name` | string or null | the name actually used |
| `title` | string or null | a title before the name |
| `sex` | string or null | `m`, `w`, or null where unknown |
| `relation` | string or null | how this person entered the tree |
| `tree` | int or null | which sub-tree of the report |
| `page` | int or null | the page of the source report |
| `parents`, `spouses`, `children` | list of int | `id`s. Kept consistent in both directions on save |
| `birth`, `death`, `burial` | date object or null | see below |
| `residences` | list | places lived, each with a place and a time |
| `occupation` | string or null | |
| `religion` | string or null | |
| `contact` | object or null | for the living, kept out of every export |
| `bio`, `extra`, `freetext` | string or null | prose |
| `note_text`, `source_text` | string or null | the raw text the parser found |
| `notes`, `sources` | list | the same, once separated |
| `events` | list | anything dated that is not birth, death or burial |
| `photo` | string or null | a file name in the tree's `fotos/` |
| `documents` | list | file names under the tree's `dokumente/<id>/` |
| `edited` | ISO date-time or null | when this person was last changed by hand |

### A date

`birth`, `death` and `burial` are each either `null` or:

| Field | Type | What it is |
|---|---|---|
| `year`, `month`, `day` | int or null | as much as is known. A year alone is normal |
| `place` | string or null | |
| `approx` | bool | true where the source said "about" |

### What is not in the file

Portraits, documents and the built page are files in the tree's folder, not
content of `baum.json`. The file names in `photo` and `documents` point at them.
A tree folder is therefore only complete with its folders — which is why handing
one over is handing over the folder, not the file.

---

## Version 2

Since 08.09.2026.  One new field on a person, `link`, and nothing else changed.

A person may be carried by more than one tree.  The case it exists for: a
wife's family grows in her own tree, not in her husband's, but she herself has
to stand in both — he needs her for his marriage, she needs herself to hang her
parents off.  The record is therefore **copied into every tree that carries
her**, not referenced, so that any one tree still opens and reads correctly on
its own.

Why the version number went up for an added field: an older program opens a
version 2 file without complaint, shows the family, and drops `link` on the
first save — silently unlinking two families. Refusing to open is the only
answer that cannot lose anything.

### `link`, on a person

`null` for everybody who is only in this tree, which is almost everybody.
Otherwise:

| Field | Type | What it is |
|---|---|---|
| `uid` | string | the shared identity, `p-` and twelve hex characters. Two records with this same value anywhere are the same person. Never reused, never changed |
| `trees` | list | every tree carrying this person: `{"slug": …, "id": int}`. The `id` differs per tree — numbers are local |
| `via` | string or null | the `uid` of the person this one arrived as a relative of. Set on everybody who travelled along with a link, `null` on the person who was linked herself |
| `hidden` | bool | hidden in **this** tree only. Never synchronised |

`uid` and `trees` are the same in every tree; `via` and `hidden` are local.

### What is written where

Saving a linked person writes the fields belonging to the *person* into every
tree in `trees`, and leaves everything belonging to the *tree* alone:

| | |
|---|---|
| written to every tree | name and its parts, sex, birth, death, burial, residences, events, notes, occupation, religion, free text, contact |
| local to one tree | `id`, `parents`, `spouses`, `children`, `photo`, `documents`, `link.via`, `link.hidden` |

The links between people are numbers, and numbers are local — which is why the
two trees may join the same person to different relatives without contradicting
each other. That is the point: her parents are in her tree, his are in his.

### Reading one without the program

A `link` can be ignored entirely. Every tree carries whole people, so a version
2 file read as if it were version 1 — skipping the unknown field — is complete
and correct for that family. Only the knowledge that two files describe one
person is lost.

---

## Version 3

Since 09.09.2026.  Two new maps on a person, and nothing else changed.

Until now a tie had no name.  `spouses` said two people belonged together but
not whether they were married, and `parents` said who somebody's parents were
but not whether they had raised them or borne them.  Both distinctions are
ordinary genealogy and both were being carried in people's heads.

The lists stay exactly as they were.  The names live beside them, keyed by the
`id` they describe, so a reader that ignores the new fields still sees every
person and every connection — it only loses what the connection was called.

### `spouse_kind`, on a person

`{}` where nothing is said.  Otherwise a map from the spouse's `id`, **written
as a string** because JSON keys are strings, to one of:

| Value | What it is |
|---|---|
| `marriage` | a marriage |
| `partner` | a partnership without a marriage |

An `id` with no entry means the tie predates the question — every couple in a
converted file has one written by the conversion, so this only happens in a file
edited by hand. It is read as `marriage`, because that is what the program has
called a couple, and drawn them as, since long before the field existed.

Being married is a fact about the pair, not about one of them, so the entry is
written on **both** records and the two must agree. Where a hand-edited file
disagrees with itself, `marriage` wins: somebody writes that on purpose, nobody
writes `partner` on purpose about a marriage.

### `parent_kind`, on a person

`{}` where nothing is said.  Otherwise a map from the parent's `id`, again as a
string, to one of:

| Value | What it is |
|---|---|
| `blood` | a biological parent |
| `step` | a step-parent |

Unlike a marriage this is **not** symmetric, and it is recorded on the **child**
— the record that says how this person came by their parents. The parent's own
record carries nothing; their `children` list is derived, and so is the role.

An `id` with no entry means nothing has been said, which is different from
saying `blood`. Most parents in a converted file are in exactly that state, and
the editor shows them as "Elternteil".

### Whether it is a father or a mother

It is not in these fields. That is the parent's `sex`, which the file has
carried since version 1, and duplicating it here would be two places to
disagree. "Vater" is a parent with `sex` `m`; "Stiefmutter" is a parent with
`sex` `w` and `parent_kind` `step`.

### The conversion out of version 2

Every existing couple is set to `marriage`. The report these trees were built
from records marriages, the program has named the tie a marriage from its first
day, and the diagram has drawn it with the double line that means one — so this
writes down what was already true rather than guessing.

Parents are left unsaid. Nothing in the source ever marked a step-parent, so
writing `blood` everywhere would invent a fact about every family in the file.

### Why the version number went up for two added fields

The same reason as version 2. An older program opens the file, shows the
family, and drops both maps on the first save — turning every recorded
partnership into a marriage and every step-parent into a blood one, silently.
Refusing to open is the only answer that cannot lose anything.
