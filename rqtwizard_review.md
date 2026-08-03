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

**STATUS: FIXED (2026-08-02), by the cheaper of the two options** — author's
choice, on the grounds that local debris can be cleaned up. The local
`orb.save` stays, because the embedded editor needs a real object; the
`'new rqt'` send moves out of `initializePage` and into
`RqtSummaryPage.finish()`, which is the single finish point for both the
functional and performance flows. So nothing reaches the repository until the
user commits.

`'new rqt'` rather than `'modified object'` for a newly-created requirement,
gated on the wizard's existing `new_req` flag: the receiver passes `new=True`
through to `on_mod_object_signal`, which is what records the object as
locally created.

The thorough fix — build the requirement in memory and save on finish — was
not taken; it is a larger change to how `PgxnObject` is embedded here.

Note the object can still reach the repository mid-wizard if the user
explicitly presses **Save** in the embedded editor on page 1. That is a
deliberate user action rather than a side effect of opening a page, and
cancelling afterwards deletes it and propagates the deletion.

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

**STATUS: FIXED (2026-08-02).** The integer list is built first and the
branch taken on that, so the placeholder cannot influence the result either
way —

```python
    prev_seqs = []
    for rqt_id in real_ids:
        try:
            prev_seqs.append(int(rqt_id.split('.')[-1]))
        except ValueError:
            continue          # e.g. the "<project>-TBD" placeholder
    seq = max(prev_seqs) + 1 if prev_seqs else 0
```

which also makes the intent (`max + 1`) legible, where the previous `while 1:`
loop computed the same thing by increment.

`gen_rqt_id`'s docstring is corrected too. With the fix the call order no
longer matters, so it now says so rather than asserting an order that was
never the one used.

Tests: `test_orb.py` test_35 gains CASE 5 (a level containing only the
placeholder returns 0) and CASE 6 (a real id alongside the placeholder still
counts only the real one). Against the pre-fix code, running the whole file,
test_35 is the only failure — `0 != 1`, which is exactly CASE 5.

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

**STATUS: FIXED (2026-08-02)** — `rqt_wizard_state['rqt_oid'] = ''` next to
the delete.

Smaller in practice than it first appears, which is worth recording:
`RqtWizard.__init__` clears every key in `rqt_wizard_state` on construction,
so the stale oid never survived into the *next* wizard anyway. What it did
survive into is the window between cancelling and whatever reads the state in
between — `pangalaxian.new_functional_rqt` does `orb.get(rqt_oid)` right after
`exec_()` returns.

---

### 4. Only the Cancel *button* discarded an unfinished requirement; closing the window did not

Found by the author while testing #1's fix (2026-08-02). Finishing worked,
Cancel worked, but closing the wizard at the last page without pressing
**Finish** left the requirement behind — saved, with its generated id, and
with none of the attributes the wizard collects, since those are applied only
in `RqtSummaryPage.finish()`.

The discard lived in `on_cancel`, wired to the Cancel button alone:

```python
        self.button(QWizard.CancelButton).clicked.connect(self.on_cancel)
```

The title-bar close button and Esc do not go near it — `QDialog` routes both
straight to `reject()`. **Verified by execution**: with `reject()` overridden
on a bare `QWizard`, close, Esc and Cancel each reach it exactly once.

**STATUS: FIXED (2026-08-02).** The discard moved into an overridden
`RqtWizard.reject()`, so all three exits get it, and the explicit Cancel
connection is gone — `QWizard` already wires Cancel to `reject()`, so keeping
it would have run the confirmation twice for a cancel and not at all for the
window's close button.

**The user is now asked before anything is discarded** (author's call). Only
once there is something to lose, though: `name` is the required field on the
first page and what `isComplete()` gates on, so an untouched requirement is
discarded without a prompt rather than nagging about nothing. Declining
leaves the wizard open — returning from `reject()` without calling
`super().reject()` cancels the close, also verified by execution.

`finish()` now clears `new_req` on success, so that a `reject()` arriving
after a completed wizard cannot delete the requirement that was just created.
`new_req` thereby means exactly "there is an uncommitted new requirement that
should be thrown away if the wizard is dismissed".

What this does **not** cover is a crash or a kill, where nothing can run —
that is the local debris the author accepted in #1.

Tests: `test/test_rqtwizard_discard.py`, 5 cases against a real, shown
wizard. Three fail against the pre-fix code, all of them the window-close
cases; the Cancel case passes both ways, as it should, and so does the
"committed requirement is not discarded" case.

**Validated against the running app (author, 2026-08-02).** All three exits
behave: Finish creates the requirement with its attributes and syncs it;
Cancel leaves nothing; closing the window prompts, and discards on
confirmation. Findings #1, #3 and #4 are settled.

*Test-setup note worth keeping:* the wizard's first page builds a real
`PgxnObject` in edit mode, so the fixture must set `state['local_user_oid']`
and `state['connected']` — without a user with `modify`, `get_perms` withholds
it, `save_button` is never created, and the page raises the same
`AttributeError` the `UNEDITABLES` change caused. `orb.icon_dir` is also
needed and is set by `pangalactic.node.startup`, not `orb.start()`; it is now
set in the shared `test_orb` fixture.


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
