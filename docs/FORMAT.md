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

### A person, in `people`

Every person carries every field. Ones that do not apply are `null`, or an empty
list where the field is a list — a person is never a short object.

| Field | Type | What it is |
|---|---|---|
| `id` | int | the number. The only thing telling two same-named people apart |
| `name` | string | the full name as shown |
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
