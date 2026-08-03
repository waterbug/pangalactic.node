# pangalactic.node review — `rqtwizard.py` (the requirement wizard), 2026-08-02

Written after live testing of the `setParent(None)` conversion
(`pangalaxian_remaining_chunks_review.md` #1) turned up an unrelated crash in
this module. The crash itself was the author's own and is already fixed; what
follows is what the incident exposed underneath it.

Context taken as given: the wizard is reached from the *New Functional
Requirement* / *New Performance Requirement* actions in `pangalaxian.py`, and
`rqt_wizard_state` is module-level in-memory state that does not survive a
restart.

---

## What triggered this review (resolved, recorded for the trail)

`RequirementIDPage.initializePage` constructs `PgxnObject(..., edit_mode=True)`
and immediately uses `self.pgxn_obj.save_button`. That attribute only exists
when `PgxnObject` resolves **both** `embedded` and `edit_mode` to true, and
`pgxnobject.py:968` refuses `edit_mode` for anything in `UNEDITABLES` —
which had gained `orb.classes['Requirement']` on 2026-07-20 (`768a9b23`), to
stop requirements being edited from the db table view. The wizard was
collateral damage:

    AttributeError: 'PgxnObject' object has no attribute 'save_button'

**RESOLVED** by the author, by taking `Requirement` back out of `UNEDITABLES`;
inhibiting db-mode editing needs a different mechanism, since `UNEDITABLES` is
global to `PgxnObject` and cannot distinguish the caller.

Two things are worth keeping from the incident. First, the failure was
**fatal, not caught** — `initializePage` is a Qt virtual, and PyQt aborts the
process on an unhandled exception in a virtual (the report ended
`Aborted (core dumped)`). Any exception on this path kills the app rather than
producing a traceback and a usable window. Second, it aborted *after* the
requirement had already been created, saved and pushed — which is finding #1.

---

## Findings (most severe first)

### 1. The requirement is created, saved, and sent to the repository before the user has entered anything
`rqtwizard.py:199-222` (`RequirementIDPage.initializePage`)

```python
    self.rqt = clone("Requirement", id=rqt_id, owner=self.project,
                     level=0, public=True)
    self.rqt.id = orb.gen_rqt_id(self.rqt)
    orb.save([self.rqt])
    dispatcher.send(signal='new rqt', obj=self.rqt)
```

Opening the wizard's first page is enough to commit a new `Requirement` to the
local db **and** push it to the repository — `'new rqt'` reaches
`on_mod_object_signal`, which calls `vger.save`. Confirmed in the incident
log: `- saved obj id: H2G2-0.0 | oid: ccc6794d-...` before the crash.

The only cleanup is `on_cancel` (153-180), which runs when the user presses
**Cancel**. Every other way out leaves the object behind, locally and on the
server:

- an exception on any wizard page (fatal, per the note above);
- the window being closed, or the app being killed;
- a crash anywhere between page 1 and the end.

The incident produced exactly this: three `Requirement` objects, all id
`H2G2-0.0`, one per crashed attempt. They are debris, not a wizard bug — each
crash aborted the process, `rqt_wizard_state` (in-memory) was lost on restart,
so the reuse guard at 207 found nothing and cloned again.

**Suggested direction, not applied.** The cheap mitigation is to stop pushing
until the user commits: keep the local save (the editor needs a real object)
but withhold `'new rqt'` until the wizard finishes, so an abandoned wizard
leaves at most local debris. The thorough fix is to build the requirement in
memory and save on finish, which is a larger change to how `PgxnObject` is
embedded here. Worth the author's judgement on which.

### 2. `get_next_rqt_seq` skips sequence 0 whenever any requirement has an unparseable id
`pangalactic.core/pangalactic/core/uberorb.py:1909-1941`

```python
    prev_seqs = [rqt_id.split('.')[-1] for rqt_id in real_ids]
    if prev_seqs:
        n = 1
        ...
        for seq in prev_seqs:
            try:
                seq = int(seq)
            except:
                continue
```

The guard is `if prev_seqs:` — *any* ids at all — but the loop that derives
`n` from them skips every id whose trailing segment will not parse as an
integer. So a list containing only unparseable ids still takes the branch,
`n` stays at its initial `1`, and the function returns **1 rather than 0**.

The wizard's placeholder id is exactly such an id: `clone(...)` is called with
`id = project.id + '-TBD'`, and `'H2G2-TBD'.split('.')[-1]` is `'H2G2-TBD'`.

**Verified by execution** against the real logic:

| requirements found | returned seq |
|---|---|
| none | 0 |
| `H2G2-0.0` | 1 |
| `H2G2-0.0`, `H2G2-0.1` | 2 |
| **only the placeholder `H2G2-TBD`** | **1** — should be 0 |
| `H2G2-0.0` + placeholder `H2G2-TBD` | 1 |

**This inverts the function's own docstring**, which says it *"assumes that
the requirement has already been saved and is therefore included in the
count"*. If that assumption held, the placeholder would be in the result set
and the first requirement in a project would be numbered `-0.1`. It comes out
as `-0.0` only because `gen_rqt_id` is in fact called at `rqtwizard.py:217`,
one line *before* the `orb.save` on 218 — the opposite of what the docstring
describes. The ordering is load-bearing and undocumented, and the docstring
actively misdescribes it.

Suggested fix: build the integer list first and branch on that, so the
placeholder cannot influence the result either way —

```python
    prev_seqs = []
    for rqt_id in real_ids:
        try:
            prev_seqs.append(int(rqt_id.split('.')[-1]))
        except ValueError:
            continue          # e.g. the "<project>-TBD" placeholder
    seq = max(prev_seqs) + 1 if prev_seqs else 0
```

which also makes the intent (`max + 1`) legible; the current `while 1:` loop
computes the same thing by increment. Then correct the docstring, or make the
call order match it — but not both independently.

### 3. `on_cancel` deletes the requirement but leaves its oid in `rqt_wizard_state`
`rqtwizard.py:176-179`

```python
                orb.delete([rqt])
                dispatcher.send(signal='deleted object', oid=rqt_oid,
                                cname='Requirement')
        self.reject()
```

`rqt_wizard_state['rqt_oid']` still names the deleted object afterwards. The
next wizard's reuse guard (207) therefore does `orb.get()` on a dangling oid,
gets `None`, and clones — so the effect is benign today, and the stale entry
is also what makes cancel-then-reopen work at all. It is worth clearing
anyway: the guard's correctness currently depends on `orb.get` returning
`None` for a deleted oid rather than on the state being accurate, and anything
else that reads `rqt_oid` (`pangalaxian.py:7105`) sees a deleted object.

One line, next to the delete: `rqt_wizard_state['rqt_oid'] = ''`.

---

## Verified correct / no findings

- **`dispatcher.connect(self.saved, 'modified object')` at 221 runs on every
  `initializePage`, and is never disconnected.** This looks like the
  accumulating-connection bug found in the admin tool
  (`pangalaxian_remaining_chunks_review.md` #2), but is not: PyDispatcher
  de-duplicates identical (receiver, signal, sender) connections. **Verified
  by execution** — three identical `connect` calls, one `send`, receiver
  invoked once. `saved()` also does no saving; it copies four fields into
  `rqt_wizard_state` and emits `completeChanged`.
- **No `cleanupPage()` override**, so pressing *Back* does not delete or reset
  the requirement. Re-entry is handled by the reuse guard at 207.
- **The 34 `setParent(None)` conversions in this module** (2026-08-02) are not
  implicated in any of the above. The crash was an `AttributeError` in
  `rqtwizard` immediately after `PgxnObject` construction; the change to
  `pgxnobject.py` in that commit was exactly two lines, both in the
  `build_from_object` teardown block, neither able to affect `edit_mode`.
