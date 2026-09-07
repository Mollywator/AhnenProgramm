# Roadmap

Ideas that are not being built yet, written so each one can become a GitHub
issue as it stands — a title, why it matters, what it would take, and what
stands in the way.

Ordered roughly by what has to exist before what.

---

## 1 · Decide the licence before this goes public

**Why.** The repository is private today and meant to become a public project
one day. `LICENSE` says MIT, which lets anybody do anything with the code,
including building it into something of their own and keeping that closed.
GPL-3.0 would instead oblige whoever passes it on to pass the source on with
it. Neither is wrong; they answer different questions about what should become
of this afterwards.

**What it takes.** A decision, and a `LICENSE` file that matches it.

**In the way.** Only that it cannot be taken back cleanly: code released under
MIT stays usable under MIT by everybody who already has it, whatever a later
commit says. So the choice belongs before the repository is made public — which
is also the moment to read every page of it once more with fresh eyes, because
publishing is the one step that cannot be undone.

---

## 2 · A map of where the family lived

**Why.** Every person already carries places — birth, death, and now a list of
residences. Drawn on a map instead of listed as text, the shape of the family
becomes visible: how far it spread, which villages it kept returning to, when
it left the region it started in.

**What it takes.** A place needs coordinates before it can be drawn, and the
places in the data are free text: *"Osterbrook, Marschland, Germany"*,
*"Hollenbeck"*, *"Neuenkirch, Suederfeld"*.

**In the way — this is the whole problem.** Turning a name into coordinates
normally means asking a service on the internet, and this program deliberately
asks nobody anything. Three ways round it, none free:

* a small gazetteer shipped with the program — the few hundred places this
  family actually uses, looked up once and stored. Offline afterwards, but
  useless to a family from somewhere else.
* coordinates typed in per place, once, by hand. Exact, tedious, and it turns
  into work nobody finishes.
* an offline extract of a public dataset such as GeoNames. Works for any
  family, costs tens of megabytes in the program.

Whichever way: the map itself is drawn offline from stored coordinates, so the
finished program still phones nowhere.

---

## 3 · Sharing between family members, without the internet

**Why.** The intended shape of this: everyone in the family runs the program,
each keeps their own branch, and the branches are handed to each other. Send
one blood line to the relatives it belongs to and the other to theirs — each
group gets the part that is theirs, and the documents that belong to it.

**What it takes.** The export already asks *what may leave the house* field by
field. This adds a second question: *whose branch*. Picking a person and a
degree — "everyone descended from my grandparents" — and exporting exactly that
subtree with its documents. The blood-relative maths for it exists already;
`bloodSet()` is what the *Ganze Linie* view is built on.

**In the way.** Nothing, as long as it stays offline: one exported file, handed
over by whatever means. It becomes a different project entirely the moment it
is meant to synchronise by itself.

---

## 4 · Certificates behind a password

**Why.** The scans are the evidence — birth certificates, church records, the
naturalisation papers. They should travel with the tree so the family holds the
proof and not only the claim. But a birth certificate of a living child is not
something to hand around unlocked, and the people who should be able to open it
in thirty years are not necessarily the people who may open it today. Hence:
included, encrypted, and the password given out separately — by hand, or in a
will.

**What it takes.** The documents in the export get packed into an encrypted
container. Everything else in the file stays readable, so the tree opens
normally and only the papers ask for a password.

**In the way — read this before starting.**

* **A lost password loses the documents.** Permanently. There is no recovery,
  that is the point of encryption. A password meant to surface after a death
  has to be findable decades later by somebody who does not know this program
  exists — that is a question about where it is written down, not about code.
* **Do not invent the encryption.** Use something that will still open in
  twenty years without this program: a 7-Zip archive with AES-256, or an
  age/GPG file. Anything self-built is both weaker and unopenable once the
  program is gone.
* Whichever is chosen, the format has to be documented in plain German
  somewhere the family will find it, next to the password.

---

## 5 · Health and illness in the family

**Why.** A family history of illness is a real medical instrument. What died of
what, what runs down which line, at what age it started — a doctor can do
something with that, and no single person can assemble it. If everyone enters
their own, everyone has it.

**What it takes.** A per-person section, kept apart from everything else, and
locked the same way the certificates are (see above). Never in an export by
default, and never quietly.

**In the way.** This is health data about living people, including children,
and about relatives who never agreed to be in the file. Three rules that would
have to hold from the first line of code:

* **Nobody enters anybody else's illnesses without being asked.** Their own,
  and their own children's while they are small.
* **Never in an export unless it is ticked, per export, every time** — no
  remembered setting for this one.
* It stays in the program's own data folder, encrypted, and never in the
  repository — which is why "program and data apart" has to come first.

---

## 6 · A shared vocabulary for places and names

**Why.** *Boehme*, *Böhme*, *Böhm*; *Hollenbeck*, *Hollenbeck bei Suederfeld*.
The same place and the same family spelled four ways, so the search misses them
and the map above cannot group them.

**What it takes.** A list of variants per place and per surname, and a search
that folds them together. Small, and it makes both the register and the map
noticeably better.

**In the way.** Nothing. It is only worth doing once there is enough hand
entered data for the variants to hurt.

---

## 7 · A separate installer, if the program ever gets big

**Why not yet.** `Stammbaum.exe` is built with PyInstaller as `--onefile`, which
means it already *is* a self extracting archive: it unpacks itself into a
temporary folder on every start, runs from there and cleans up afterwards.
Measured three times on the machine it was built on: **1.3, 1.1, 1.2 seconds**
from double click to ready. There is nothing an installer would improve, and it
would turn two files to hand over into three.

**When it changes.** Unpacking cost grows with the program. GEDCOM support and,
much more, an offline gazetteer for the map (idea 2) could push it into tens of
megabytes, and then a second of unpacking becomes five.

**What it takes then.** Build with `--onedir` instead, and wrap the folder in
one small installer that unpacks once and leaves a `Stammbaum.exe` behind. The
start is then instant, at the cost of an install step - which is the right
trade only once the start is actually slow. Measure before switching.
