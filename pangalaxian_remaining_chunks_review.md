# pangalactic.node review — `pangalaxian.py`, pubsub dispatch, deletion, tree/dashboard, admin (2026-07-31)

Fifth and final installment of the `pangalaxian.py` review, covering the
chunks listed as outstanding at the top of
`pangalaxian_handlers_review.md`:

- `on_pubsub_msg`'s full dispatch table (~2074-2324);
- `on_deleted_object_signal` (~4427-4770) and `del_object` (~4770-4853);
- the admin-tool RPC result handlers (~2343-2426) and `do_admin_stuff`;
- the tree / dashboard machinery — `update_object_in_trees`,
  `refresh_tree_views`, `rebuild_dashboard`, and the mode-setup methods.

**Coverage honesty:** the import/export and file up/download actions were
spot-checked for the patterns below rather than read line by line, and the
tree/dashboard functions were read for structure and failure handling rather
than for correctness of the Qt model index arithmetic, which would need the
running app to judge. Findings 1 and 6 came out of that pass; I would not
claim those areas are exhausted.

Line numbers are as of the `#1/#4/#5` fixes and the `des set` removal
recorded in the previous installment.

---

## Findings (most severe first)

### 1. The widget "detach" idiom does not detach: `.parent = None` shadows `QWidget.parent()`
~55 sites across 8 modules (`pangalaxian.py`, `pgxnobject.py`,
`rqtwizard.py`, `dialogs.py`, `wizards.py`, `filters.py`,
`blockmodeler.py`, `timeline.py`)

The established idiom for tearing down a widget in this codebase is:
```python
    ld_widget.setAttribute(Qt.WA_DeleteOnClose)
    ld_widget.parent = None          # <-- intended: ld_widget.setParent(None)
    ld_widget.close()
```
`parent` is a **method** on `QWidget`, not a writable property. Assigning to
it does not reparent anything — PyQt allows the attribute assignment, which
simply shadows the bound method on that instance. Two consequences:

- **The detach silently does not happen.** The widget remains a child of its
  Qt parent. Where the surrounding code relies on `WA_DeleteOnClose` plus
  `close()`, the object still gets destroyed and the mistake is masked; where
  it does not (no `WA_DeleteOnClose`, or `close()` not reached), the widget
  stays parented and alive.
- **Any later `widget.parent()` call raises** `TypeError: 'NoneType' object
  is not callable`, which is a confusing way to discover the problem. This is
  a plausible contributor to the "C++ object got deleted" class of failure
  that several bare `except:` blocks in this file are written to swallow
  (see #6).

Representative sites in `pangalaxian.py`: 5161, 5174, 5267, 5278, 5292, 5641,
5727, 5774, 5869, and five in `new_product_wizard` (6514-6562).
`rqtwizard.py` alone has ~30.

**Explicitly excluded:** `systemtree.py:56, 195, 201, 318, 327`. Those are on
`Node` and `FakeRoot`, which subclass plain `object`, where `self.parent` is
a legitimate data attribute and nothing is shadowed. Verified before
reporting.

**Caution on the fix.** Mechanically converting all ~55 to `setParent(None)`
is *not* a safe no-op: it would make the reparenting actually happen, which
changes Qt ownership and object lifetime — a widget with no parent and no
`WA_DeleteOnClose` becomes a top-level window and is no longer deleted by its
parent. Each site needs checking against whether `WA_DeleteOnClose` is set
and whether `close()` follows. Worth doing, but as a deliberate pass with the
app running, not a sed.

### 2. Admin-tool signal connections accumulate on every open, and `self.admin_dlg` is dereferenced unguarded
`pangalaxian.py:7250-7266` (`do_admin_stuff`), `2357`, `2424`

`do_admin_stuff` builds a **new** `AdminDialog` on every invocation and adds
two more permanent connections:
```python
    self.admin_dlg = AdminDialog(org=self.project, parent=self)
    ...
    self.refresh_admin_tool.connect(self.admin_dlg.refresh_roles)
    dispatcher.connect(self.admin_dlg.refresh_roles, "deleted object")
    self.admin_dlg.show()
```
Nothing disconnects the previous dialog's connections — **there is no
`disconnect` call anywhere in `pangalaxian.py`** (verified). And
`AdminDialog` does *not* set `Qt.WA_DeleteOnClose`; the only
`WA_DeleteOnClose` in `admin.py` (line 433) belongs to `AddPersonDialog`, a
different class. Since each dialog is created with `parent=self`, closing it
merely hides it and it stays alive as a child of the main window for the rest
of the session.

So opening the admin tool N times leaves N live `AdminDialog` instances, all
still connected to `refresh_admin_tool` and to the `"deleted object"`
dispatcher signal. Deleting one object then runs `refresh_roles` on all N,
N-1 of them invisible. `AdminDialog.__init__` also dispatches
`'get people'` (admin.py:529), so each open fires another
`vger.get_people` RPC.

Two related unguarded dereferences of `self.admin_dlg`:
- `on_rpc_add_person_result:2357` — `self.admin_dlg.on_person_added_success(...)`.
  Note the very next block *does* guard its dialog access with
  `getattr(self, 'person_dlg', None)`, so the inconsistency is visible in
  the same function.
- `on_rpc_get_people_result:2424` — `self.admin_dlg.on_got_people()`, and it
  sits in a **`finally:`**, so it runs even when the `try` above it failed.

Both raise `AttributeError` if the admin tool was never opened in this
session. Reachability is currently limited by the fact that `'get people'`
is only sent from `AdminDialog.__init__` — but that send happens *during*
construction, i.e. before `self.admin_dlg` has been assigned, so the code
depends on the RPC never resolving synchronously.

Fix: disconnect (or reuse a single dialog instance) in `do_admin_stuff`, and
guard both dereferences with `getattr(self, 'admin_dlg', None)` to match the
convention already used for `person_dlg`.

**STATUS: FIXED.** `do_admin_stuff` now disconnects the previous dialog from
both `refresh_admin_tool` and the `"deleted object"` dispatcher signal, then
closes and `deleteLater()`s it, before building the new one. Both
dereferences are guarded with `getattr(self, 'admin_dlg', None)`.

**Verified by execution** with real `pydispatcher` and real PyQt5 signals,
opening the tool three times and then firing one deletion:

| | `"deleted object"` → `refresh_roles` on | `refresh_admin_tool` → on |
|---|---|---|
| pre-fix | `['dlg1', 'dlg2', 'dlg3']` | `['dlg1', 'dlg2', 'dlg3']` |
| post-fix | `['dlg3']` | `['dlg3']` |

*Note on the test, since it nearly produced a false negative:* a first
attempt showed `['dlg3']` for **both** cases, i.e. no leak to fix. The cause
was that the stand-in dialogs were created without a Qt parent, so the
superseded ones were garbage collected and their connections died with them —
pydispatcher holds receivers weakly. The real code passes
`AdminDialog(org=..., parent=self)`, and it is precisely that parent
ownership which keeps the old dialogs alive. Adding `parent=` to the
stand-ins reproduced the accumulation. Worth recording because it is the
mechanism of the bug: **the leak exists only because the dialogs are
parented**, and any fix that relies on garbage collection instead of explicit
disconnection would not work here.

### 3. `del_object`'s "db" mode branch sets a flag that nothing on its path can consume
`pangalaxian.py:4825-4826`, with `on_vger_get_parmz_result:4032`

```python
    elif self.mode == 'db':
        state['update db table'] = True
```
`state['update db table']` has exactly one consumer, at 4032 — and it is
nested **inside** the `if state.get('updates_needed_for_remote_obj_deletion'):`
branch of `on_vger_get_parmz_result`. That key is set only on a *remote*
deletion (4515). So on a deletion routed through `del_object`:

- **offline** — `get_parmz()` is never called (it is gated on `connected`),
  so the flag is never read;
- **online** — `get_parmz()` *is* called (4848), but
  `updates_needed_for_remote_obj_deletion` is empty for a local delete, so
  the `else:` branch runs and 4032 is not reached.

Either way the flag stays set and the db table is not refreshed, so the
deleted object remains visible in the table view. Compare
`on_deleted_object_signal:4484-4488`, which handles the same case by calling
`filter_panel.remove_object(oid)` directly.

**Reachability caveat, stated honestly:** this depends on a deletion reaching
`Main.del_object` while `self.mode == 'db'`. `del_object` is connected to the
`deleted_object` pyqtSignal (451), the diagram widget (3177), the three
`ModelWindow` instances (5680, 5689, 5701) and the admin dialog (7256); the
db table's own deletion path goes through `ObjectTableModel.del_object`
(`tablemodels.py:476`), a different method. So the combination may be rare in
practice. The branch is nonetheless wrong as written, and the cheap fix is to
mirror what `on_deleted_object_signal` does rather than set a flag.

> **Context for #3 and #4 both** (author, 2026-08-01): **pydispatcher is the
> target for all signalling, and every `pyqtSignal` in this package is a
> legacy detour being removed.** It was adopted after an elusive bug was
> mistakenly attributed to pydispatcher; by the time the real cause was found,
> too many signals had been converted for reverting to be worth prioritising.
>
> That resolves what the two functions below are *for*: `del_object` is
> reached almost entirely through **pyqtSignal** connections, while
> `on_deleted_object_signal` handles the **dispatcher** signal. They are not
> two designs — they are the two sides of a stalled migration, which is why
> they duplicate a dispatch block and have drifted. The durable fix for #4 is
> therefore not "extract a shared helper" but "finish the migration and delete
> `del_object`", folding anything it does that the dispatcher path does not
> into `on_deleted_object_signal`.
>
> Also worth reading with this in mind: a commented-out `.emit(...)` in this
> package is more likely a half-finished removal than an oversight — mistaking
> one for the other produced a wrong finding in `admin_tool_review.md` #1,
> since retracted.

## Appendix: how far the pydispatcher migration has actually got

Measured 2026-08-01, and smaller than it looks from the inside. Counting raw
`.connect(` calls badly overstates it, because most are ordinary widget wiring
(`button.clicked.connect(...)`) where the emitter *is* the receiver's owner —
that is a fine use of Qt signals and not what the migration is about.

**Totals:** 140 `dispatcher.connect` calls against **33** custom `pyqtSignal`
declarations and **43** live `.emit(...)` calls.

Of those 43 emits, roughly half are **not migration debt at all** and should
stay:

| category | examples | why it stays |
|---|---|---|
| Qt model/view protocol | `dataChanged.emit`, `completeChanged.emit`, `editingFinished.emit` | required by `QAbstractItemModel` / `QWizardPage`; not application signalling |
| worker threads | all of `threads.py`, plus `progress_signal.emit` | cross-thread delivery is exactly what Qt signals are for; pydispatcher is not a thread-safe substitute |

That leaves **~21 live emits of custom domain signals**, across eight modules
— `admin.py`, `dashboards.py`, `dialogs.py`, `filters.py`, `libraries.py`,
`pangalaxian.py`, `pgxnobject.py`, `systemtree.py`. Recurring names:
`obj_modified` (5 sites), `delete_obj` (2), `units_set` (3),
`deleted_object` / `new_object` (3), plus `hw_fields_edited`,
`rqt_parm_mod`, `toggle_library_size`, `activity_edited`, `remote_frozen`,
`remote_thawed`, `refresh_admin_tool`.

**Three modules were already fully migrated** — `blockmodeler.py`,
`diagrams/shapes.py` and `diagrams/view.py` have **zero** live emits; every
`.emit(...)` in them was commented out. This is also the clearest evidence for
reading a commented-out emit as a completed removal rather than a bug: in the
diagram code, that is exactly what they were.

**DONE (2026-08-01): the diagram subsystem is now pyqtSignal-free.** Removed:

- the two vestigial declarations, `ModelWindow.deleted_object`
  (`blockmodeler.py`) and the diagram scene's `deleted_object`
  (`diagrams/view.py`), each replaced by a short note saying what was there
  and why it went;
- the **three live `self.system_model_window.deleted_object.connect(
  self.del_object)` calls in `pangalaxian.py`** — these had to go with the
  declaration or the removal would have failed at runtime rather than at
  import, since nothing ever emitted the signal they connected to;
- six stale commented-out emits/connects referring to the removed signals
  (five in `diagrams/shapes.py`, one each in `view.py` and `blockmodeler.py`)
  — once the signal is gone, a comment referencing it is actively misleading;
- the now-unused `pyqtSignal` import in both modules.

Custom declarations across the package: **31 → 29**. (The "33" quoted above
was a loose count that included two commented-out declarations.) Verified by
importing `ModelWindow` and `DiagramScene` and confirming neither still has a
`deleted_object` attribute.

Nothing else changes behaviourally: deletions from the diagram were already
announced with `dispatcher.send('deleted object', ...)`, which
`on_deleted_object_signal` handles — including calling `vger.delete`.

**On `Main` itself the surface is three signals** — `deleted_object`,
`new_object`, `mod_object` — and the connection block that sets them up
(451-455) is explicitly separated from the ~50 dispatcher connections that
follow it. Two of the three already delegate straight through thin adapters
(`on_new_object_qtsignal` / `on_mod_object_qtsignal` both just resolve the oid
and call `on_mod_object_signal`), so converting their emitters to
`dispatcher.send` and deleting the adapters is mechanical. `deleted_object` →
`del_object` is the one with real behaviour behind it, and is the subject of
#4 above.

### 4. `del_object` and `on_deleted_object_signal` duplicate the same dispatch block and disagree in one branch
`pangalaxian.py:4818-4842` vs `4468-4504`

The two functions carry near-identical ~25-line mode/cname dispatch blocks.
In the `component`-mode branch they differ, and only one of them can be
right:

| | `on_deleted_object_signal` (4489-4497) | `del_object` (4827-4835) |
|---|---|---|
| body | `set_product_modeler_interface()` then `self.system_model_window.on_signal_to_refresh()` | `set_product_modeler_interface()` then `state['diagram needs refresh'] = False` |

`del_object` **clears the "needs refresh" flag without performing a
refresh**. If `set_product_modeler_interface()` already rebuilds the diagram,
then clearing the flag is correct and `on_deleted_object_signal`'s extra
`on_signal_to_refresh()` is redundant work; if it does not, `del_object`
suppresses a refresh that was needed and a later `get_parmz` callback will
skip it because the flag reads `False`. One of the two is wrong and I cannot
tell which without the running app — hence reporting the divergence rather
than a fix.

The duplication itself is the underlying problem: these blocks have already
drifted, and will drift again. They are a natural candidate for a single
shared `_post_deletion_updates(cname, oid)` helper.

### 5. `on_pubsub_msg` uses `return` where it means `continue`, and shadows `userid`
`pangalaxian.py:2082-2324`

The handler is written as a loop over message items:
```python
    userid = state.get('userid', '')
    for item in msg.items():
        subject, content = item
```
but two things in the body assume a single iteration:

- **`return` instead of `continue`** at 2099, 2108, 2119 (the "ignore, it was
  my own action" paths) and 2171 (unknown project/link). Each abandons the
  whole message, not just the current subject.
- **`userid` is reassigned by the `'new mode defs'` branch** at 2125
  (`md_dts, project_oid, md_data, userid = content`), clobbering the
  outer local for any subsequent iteration. A later `'new'`/`'modified'`/
  `'decloaked'` item in the same message would then compare `authid` against
  the *publisher's* id rather than the local user's, and either drop a real
  update or process one of its own.

**Latent, not live:** every `self.publish()` call in `vger.py` sends a
single-key dict (checked all 29), so the loop always runs exactly once. But
the loop's existence advertises multi-subject support that the body cannot
honour, and the failure mode if one is ever sent is silent message loss.
Cheap to make honest: `continue` in place of `return`, and rename the
unpacked variable (e.g. `md_userid`).

**STATUS: FIXED.** All four `return`s are now `continue`, and both mode-def
branches unpack `md_userid` instead of `userid`. Note the
`'comp mode datum updated'` branch (2159+) had the **same** shadowing, which
the original write-up missed — it unpacks `userid` from `content` at 2162 and
has its own `return` at 2180; both are fixed too.

**Verified by execution**, with the loop bodies transcribed:

| case | pre-fix | post-fix |
|---|---|---|
| multi-subject msg, first subject is my own action | returns early — the second subject is **never handled** | first ignored, second handled |
| `'new mode defs'` from another user, then a `'modified'` item | the `'modified'` item is **dropped** (compared against the clobbered `userid`) | both handled |
| `'new mode defs'` that really was my own action | ignored | ignored (regression preserved) |

**A trap worth recording:** renaming the unpacked variable is not sufficient
on its own. The two uses below it — the debug log line and, critically,
`if userid == state.get('userid'):` — also had to be updated. Renaming only
the assignment would leave that test comparing the *local* userid against
itself, making it **always true**, so every remote mode-def update would be
silently discarded as "my own action". That would have been a worse bug than
the one being fixed.

### 6. `update_object_in_trees` wraps 60 lines in a bare `except:` attributed to one specific cause
`pangalaxian.py:5552-5618`

```python
        try:
            ...  # ~60 lines of tree/model index manipulation
        except:
            # sys_tree's C++ object had been deleted
            orb.log.debug('* update_object_in_tree(): sys_tree C++ object '
                          'might have got deleted, cannot update.')
```
The comment names one cause, but the handler catches everything raised
anywhere in the block — `AttributeError` on a corrupted `Acu`/`PSU`,
`IndexError` from model index arithmetic, a genuine bug in `setData` — and
reports all of them at `debug` level as the same benign-sounding condition.
Any defect in the tree-update logic is therefore invisible in normal
operation.

This is the sharpest instance of the file's systemic bare-`except:` pattern
(**98** occurrences in `pangalaxian.py`), and the one most likely to be
hiding something, because the guarded region is large and does real model
mutation. Narrowing it to catch `RuntimeError` (which is what PyQt raises for
a deleted C++ object) and letting everything else propagate — or at minimum
logging at `error` with the traceback — would make the actual failure
visible.

---

## Verified correct / no findings

- **`del_object`'s GUI updates are not connectivity-gated** (4818-4842), so a
  local deletion while connected does update the tree, dashboard and diagram.
  I initially suspected a gap here, because `on_deleted_object_signal`'s
  update block *is* gated on `not connected` (4465) and its remote block
  requires `remote and connected` (4505) — leaving an apparent hole for
  "local delete while connected". `del_object` covers that case, and the two
  functions serve different entry points (direct call vs. dispatcher signal
  from another component). No bug — but the interaction is subtle enough to
  be worth recording, and it is the same overlap that produced #4.
- **`state['system']` is safe to subscript** at 4518 and 4548 despite the
  unguarded `state['system'][...]` form, because `Main.__init__:385-386`
  guarantees it is a dict (`if not state.get('system') or isinstance(
  state['system'], str): state['system'] = {}`). The mixed styles in the same
  file (`(state.get('system') or {}).get(...)` at 4449 and 4798 vs.
  `state['system'][...]` at 4548) are cosmetic rather than a latent
  `KeyError`.
- **The `'frozen'` and `'thawed'` pubsub branches** (2204-2271) both check
  local presence before acting and tolerate an empty payload; `'thawed'`
  additionally validates the list shape and logs "bad format" rather than
  raising.
- **`on_rpc_get_people_result`'s `try/except/finally`** correctly isolates
  the per-row unpacking so a malformed row does not abort the whole result —
  the only problem there is the unguarded `admin_dlg` in the `finally`
  (finding #2).

## Status summary

**Fixed** (2026-07-31), both verified by execution and annotated inline:

- **#2** admin-tool connection accumulation, plus the two unguarded
  `self.admin_dlg` dereferences.
- **#5** `return` → `continue` in the pubsub loop, and the `userid` shadowing
  in *both* mode-def branches.

**Open:**

- **#1** the `.parent = None` idiom (~55 sites) — deliberately deferred; the
  fix changes Qt ownership semantics and wants the app running.
- **#4** the divergent component-mode branch — needs your judgement on which
  behaviour is correct.

**Fixed since (2026-08-02):**

- **#3** `update db table` — **FIXED.** `del_object`'s "db" branch now calls
  `filter_panel.remove_object(oid)` directly, mirroring
  `on_deleted_object_signal`, instead of setting a flag nothing on that path
  could read. Note this is the cheap fix, not the durable one: per the context
  note above, the durable fix is finishing the pydispatcher migration and
  deleting `del_object` altogether, at which point this branch goes with it.
  Not covered by an automated test — it needs a live `object_tableview` in
  "db" mode; the change is a direct mirror of the adjacent handler, and the
  review's own reachability caveat still applies.
- **#6** the over-broad `except:` in `update_object_in_trees` — **FIXED.**
  `RuntimeError` (the genuine deleted-C++-object case) keeps the original
  benign debug message; anything else is now named at *error* level instead of
  being reported as a deleted C++ object. Both are still swallowed, because
  this runs inside rpc callbacks where raising would break the chain.

## Original suggested fix order

1. **#2 admin-tool connections** — a real leak with visible consequences
   (duplicate RPCs and repeated `refresh_roles` on hidden dialogs) after the
   second open, plus two one-line `getattr` guards.
2. **#5 `return` → `continue` and the `userid` shadow** — trivial, and makes
   the handler match the contract its own loop advertises.
3. **#4 the divergent component-mode branch** — needs your judgement on which
   of the two behaviours is correct; consolidating the duplicated block into
   one helper is the durable fix.
4. **#3 `update db table`** — mirror `on_deleted_object_signal`'s direct
   `remove_object(oid)` call instead of setting an unconsumable flag.
5. **#6 narrow the `update_object_in_trees` except** — cheap, and likely to
   surface whatever it is currently hiding.
6. **#1 the `.parent = None` idiom** — the largest, and deliberately last:
   the fix changes Qt ownership semantics and wants the app running to
   validate. Worth a dedicated pass rather than folding into other work.
