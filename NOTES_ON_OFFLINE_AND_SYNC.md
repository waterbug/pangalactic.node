# Design note: offline work and later sync

Written 2026-07-26, following the `pangalaxian.py` sync-machinery review.
Context: historically Gargleblaster's dominant use has been a fully
connected, real-time collaborative state, and the offline paths have not
had attention. The anticipated future paradigm is **both** — highly
collaborative connected work *and* offline work that is synced later. This
note assesses what exists today, identifies the one place where the current
behaviour is load-bearing in a way that blocks a naive fix, and lays out
the decisions that need making.

Everything in "Current state" was verified by execution against the test
fixtures. Everything in "Decisions required" is a proposal, not a finding.

---

## 1. Current state

### What already round-trips

Of the three basic mutations, two already survive a disconnect:

| operation | offline behaviour | on reconnect |
|---|---|---|
| **create** | object created locally, `creator` = local user | pushed — `on_sync_result` collects `created_objs` (objects unknown to the server whose creator is the local user) and sends them via `vger.save` |
| **edit** | `on_save` bumps `mod_datetime` | pushed — the server reports the oid in "earlier on server" (`data[2]`), the client puts it in `objs_to_save` and sends it via `vger.save` |
| **delete** | object removed from the local db | **nothing.** `del_object` only calls `vger.delete` `if state.get('connected')`, and no queue records the deletion |

So the deletion gap is a targeted omission rather than missing
infrastructure — creates and edits already have working paths to build on.

### What is broken or missing

1. **Deletions are silently reverted.** With no queue, the repository is
   never told. Both sync paths then restore the object, because each treats
   "the client did not report this oid" as "the client needs it"
   (`vger.sync_project`'s `newer_objs`, and `sync_library_objects` via
   `earlier(None, dt) == True`). This applies to *authorized* deletions of
   the user's own work just as much as to unauthorized ones — ordinary
   intended usage is quietly undone.

2. **Offline permissions are inverted.** `state['synced_oids']` is assigned
   in exactly one place (`pangalaxian.py:1431-1433`) from
   `self.local_user.created_objects` — only the user's *own* objects. Since
   `access.py:173-180` grants full permissions to any object *not* in that
   list, the effect is the opposite of the comment's stated rationale: the
   user gets `modify` + `delete` offline on precisely the objects they did
   **not** create. (Confirmed independently in the running app.)

3. **Rejected work disappears without a word.** At
   `pangalaxian.py:1441`, `valid_objs_to_save = [obj for obj in
   objs_to_save if 'modify' in get_perms(obj)]` runs at sync time, while
   connected, so it evaluates real permissions and correctly stops
   unauthorized offline edits from reaching the repository. But objects
   failing the filter are simply omitted — no notification, no record of
   what was dropped — and the local object keeps its modified values. Its
   `mod_datetime` stays newer than the server's, so every subsequent sync
   re-derives it, re-filters it out, and drops it again. **The edit lives
   locally forever, looks saved, never reaches the repository, and never
   produces an error.**

4. **No reconciliation reporting exists at all.** There is nowhere in the
   sync chain that reports "these N changes could not be applied, and here
   is why". `on_failure` only logs a traceback, and the login/sync chain is
   a long `addCallback`/`addErrback` ladder on one deferred where each
   errback catches only the preceding link — so a mid-chain failure leaves
   the sequence half-completed, silently.

---

## 2. The crux: the current bug is load-bearing

This is the most important thing in this note, and it invalidates the
obvious fix.

The natural repair for problem 2 is "make `synced_oids` record every oid
confirmed present on the server, not just the user's own". But
`access.py`'s permission logic is:

```python
server_or_connected_client = server or (client and connected)
```

and *every* normal grant of `modify`/`delete` — including the
creator branch at 189-198 — is gated on `server_or_connected_client`. For a
disconnected client that is always False. The **only** path that grants
write permission offline is the `object_not_synced` branch at 173-180.

Measured, on an object created by the local user (their own work):

| offline, object … | resulting perms |
|---|---|
| **not** in `synced_oids` (today's behaviour) | `['add docs','add models','delete','modify','view']` |
| **in** `synced_oids` (after the naive fix) | `['view']` |

So today, offline editing works *only because of the bug*. Correcting
`synced_oids` in isolation would not tighten offline permissions to match
online ones — it would reduce the user to **view-only on everything,
including their own work**, and eliminate offline editing entirely. That is
the opposite of the goal.

**Therefore the offline permission model has to be designed, not patched.**

---

## 3. Decisions required

### 3.1 What should offline permission mean?

The current model conflates two different questions into one boolean. They
should be separated:

- **May this user modify this object at all?** — a function of role,
  creator, ownership, and CM state (frozen). Connectivity is irrelevant to
  this question.
- **Is it safe to modify it right now, offline?** — a function of conflict
  risk: how likely is it that someone else is changing the same object, and
  how bad is the merge if they are?

A workable shape: let `get_perms` answer the first question independently of
connectivity, and introduce a separate notion — call it *offline
eligibility* — answering the second. An object would be offline-editable
when the user has the right in principle **and** the conflict risk is
acceptable.

Conflict risk is where the policy judgement lives, and it is genuinely a
domain decision rather than a technical one. Plausible inputs: whether the
object is project-owned versus a personal/library item; whether it is
frozen; whether the user is the sole role-holder for its discipline;
whether it was checked out deliberately before going offline.

**An explicit check-out model is worth considering** given the CM
orientation of the application: before disconnecting, the user selects what
they intend to work on, the client records it, and offline editing is
confined to that set. That maps cleanly onto existing CM concepts, makes
the offline scope visible to the user, and — if the server is told —
makes it visible to collaborators too. It is more work than a heuristic,
but it removes conflict ambiguity almost entirely.

### 3.2 Deletion queue

Record deletions that occur while offline and replay them during the sync
handshake:

- Persist an oid queue alongside the existing `trash`/`deleted` caches in
  the home directory (same yaml treatment, and note the write-safety fix
  already applied to those readers/writers in `p.core/__init__.py`).
- Replay as `vger.delete` calls early in the sync sequence, **before** the
  project/library syncs that would otherwise restore the objects.
- The server authorizes each one normally, so unauthorized deletions get a
  clean explicit rejection instead of a silent reappearance.
- Entries clear only on confirmed server acceptance, so an interrupted sync
  retries rather than losing the deletion.

Note the ordering constraint: replay must precede `sync_project` /
`sync_library_objects`, or the restore-then-delete sequence will produce
visible churn.

### 3.3 Conflict policy

Today's policy is last-write-wins by `mod_datetime`, decided per object.
That is defensible for short disconnects and probably inadequate for long
ones. Worth deciding explicitly:

- Is a silent overwrite of someone else's newer change ever acceptable?
- Should conflicts be surfaced for the user to resolve, and at what
  granularity — whole object, or per field/parameter?
- Do parameters and data elements need different treatment from object
  attributes? They live in separate caches with their own sync path
  (`get_parmz`, `on_vger_get_parmz_result`), so they can be handled
  differently if that is useful.

### 3.4 Reconciliation reporting

This is the piece that most determines whether offline work feels
trustworthy. The sync handshake should end with a user-visible summary:
what was pushed, what was rejected and why, what was restored, what
conflicted. At minimum, the `pangalaxian.py:1441` filter must stop
discarding work silently — it should collect rejected objects and report
them rather than omitting them.

**Most of the data already exists — only the presentation is missing.**
Live testing (5.A) confirmed `vger.save` returns the refused object ids in
`unauth`. The client receives them in `on_vger_save_result`
(`pangalaxian.py:3795-3843`) and then throws them away:

```python
if stuff.get('mod_obj_dts'):
    msg = '{} modified; '.format(...)      # assignment, not +=
if stuff.get('unauth'):
    msg = '{} unauthorized (not saved); '.format(...)   # overwrites the above
if stuff.get('no_owners'):
    msg = '{} no owners (not saved); '.format(...)      # overwrites again
if not msg:
    msg = 'nothing to save; synced.'
    self.statusbar.showMessage('synced.')   # ONLY reached when nothing happened
```
Three defects in nine lines: each branch **assigns** `msg` instead of
appending, so only the last category survives; every branch logs at
**debug** level only; and `showMessage` is called *exclusively* in the
`not msg` branch — so the status bar says "synced." when nothing happened
and says **nothing at all** when work was refused. Turning this into an
accumulated, user-visible summary is a small, self-contained change and is
the highest value-per-effort item in this note.

The gap that genuinely has no data behind it is the **stale-edit** case
(5.C): a conflict-dropped edit appears in neither `unauth` nor
`mod_obj_dts`, so the client cannot currently detect it at all. Reporting
that requires a protocol change — e.g. `vger.save` returning a `stale` or
`conflicted` list alongside `unauth` — which is worth folding into the 3.3
decision.

A secondary question: what should happen to locally-modified objects the
server refuses? Leaving them diverged (today's behaviour) means the client
retries and re-drops them forever. Options are to revert them to the server
copy, keep them but mark them clearly as unsynced, or offer the user the
choice. This should be a deliberate decision.

### 3.5 The authoritative caches

`parameterz`, `data_elementz`, and `mode_defz` are the three caches not
derivable from the database, persisting only as their json files. The
server's copies are authoritative and clients re-sync from them, so
client-side loss is recoverable — *while connected*. Extended offline use
makes the client's copies the sole record of offline parameter work for
longer, which raises the value of the write-safety fix already applied to
`save_parmz`/`save_data_elementz`/`save_mode_defz` and argues for treating
these caches as first-class sync participants rather than a side channel.

**Update (2026-07-31): "first-class sync participants" is now a measured
requirement, not a preference.** Offline parameter work is currently lost
outright — a parameter-only edit never stamps `mod_datetime`, so the object
is never pushed; `on_parms_set` is connectivity-gated and queues nothing; and
`parameterz.update(<entire server cache>)` on reconnect replaces each per-oid
dict wholesale, reverting the local value. A parameter *added* offline is
dropped entirely. Verified end to end — see
`pangalaxian_handlers_review.md` #2.

This is a sharper case than §5.C: there, an unauthorized or stale edit is
discarded but the local object stays diverged; here the local value is
actively reverted to the server's, so there is nothing left to notice.

Two things follow:
- It belongs in the 3.3 conflict-policy and 3.4 reporting decisions, not
  beside them. Parameters are not a minor annex of the data model — see the
  ontology-explosion rationale now recorded in
  `pangalactic.core/NOTES_ON_CHECKOUT_MODEL.md` §4: there are roughly an
  order of magnitude more parameters than ontology properties, which is
  precisely why they live in caches, and why the bulk of engineering content
  travels this path.
- The author has settled the shape of the fix: **offline parameter and
  data-element adds/mods/deletes are permitted only for checked-out
  ("locked") objects, and behave exactly as regular attribute editing does.**
  See §4a of the check-out note for the three requirements that implies
  (permission, persistence, reconciliation).

**And a constraint on how *not* to fix it.** The wholesale
`parameterz.update()` in `on_vger_get_parmz_result` must stay. Merging
per-oid was tried, and in highly active collaborative use clients drifted out
of sync; full replacement fixed it. The replacement is a convergence
mechanism — it corrects any local drift on every sync, where a merge would
let a divergent entry persist forever. `get_parmz` runs at the tail of the
save chain, so the push has already happened by the time the pull replaces
the cache. **Protect offline work by guaranteeing the push, never by
weakening the pull** — which is the same ordering rule §3.2 states for the
deletion queue.

### 3.6 CM interaction

Freeze already requires connectivity, and thaw now does too (both check
`state['connected']`). That is the right default — CM state changes are
repository-wide facts and should not be made unilaterally offline. Worth
confirming that intent explicitly, since an offline-first paradigm will
otherwise invite pressure to relax it.

### 3.7 Parameter / data element deletion queue — as built (2026-08-02)

The parameter-level counterpart of §3.2, and the fix for the loss recorded
in §3.5. The two halves turned out to need different treatments, which is
worth stating plainly because the asymmetry is not obvious:

**Additions and modifications need no queue.** They are carried in the
object's own serialization (`parameters` / `data_elements`), so they reach
the repository whenever the object is pushed. What was actually missing was
the push: the parameter drop handlers in `pgxnobject` did not stamp
`mod_datetime`, so the object was never considered modified and never went
up. The data-element drop handler alongside them *did* stamp — the two paths
had simply drifted apart. Both parameter drop sites now stamp and save, the
same treatment already applied to parameter *edits*.

**Deletions cannot travel that way, and do need a queue.**
`deserialize_parms` **merges**: it assigns each pid present in the incoming
dict and never removes one that is absent. "This pid is gone" and "this pid
was not mentioned" are therefore indistinguishable to the server, so a
parameter deleted offline survives there and is handed straight back by the
next `get_parmz()`. Note this is not a defect to be fixed in
`deserialize_parms` — merge-on-deserialize is what lets a partial push be
safe. The deletion simply needs its own explicit signal.

So `p.core.parm_del_queue` records deletions that could not be sent:

    {'kind|oid|id': {'kind': 'parm'|'de', 'oid': str, 'id': str,
                     'datetime': str}}

keyed so it is self-deduplicating, written to its own file the moment an item
is queued (a queued deletion lost in a crash comes back silently — the exact
failure the queue exists to prevent), and read back in `orb.start()` so it
survives restarts, since offline work spans sessions.

**Ordering.** The replay is chained *ahead of* `get_parmz()` inside
`get_parmz()` itself, not merely placed early in the sync chain. `get_parmz`
is also reached directly from the "parameters set" pubsub handler, which can
arrive at any moment after reconnecting — early placement in the chain would
have made the ordering incidental rather than guaranteed. `replay_parm_del_queue()`
returns a `DeferredList` so the pull can genuinely wait on the push, and is a
no-op when the queue is empty, which is the usual case. Push before pull,
per §3.5.

Entries clear only on repository confirmation, so an interrupted sync retries
rather than dropping the deletion; malformed entries are discarded rather
than retried forever.

### 3.8 Authorization on the single-item parm/de rpcs (2026-08-02)

Found while doing §3.7, and wider than first reported: not just
`vger.del_parm` and `vger.del_de` but also `vger.add_parm` and `vger.add_de`
performed **no authorization check at all**. Any user could add or remove
any parameter or data element on any object, and all four always reported
success. Their batch equivalents `set_parameters()` and `set_data_elements()`
had always checked `"modify"` perms — these four had simply been missed. The
pre-fix logs show how little was validated: `add_parm(oid=None, pid=P)`
published a "parm added" message with a null oid.

All four now resolve the caller from `cb_details.caller_authid` and require
`"modify"` in `get_perms(obj, user)` before mutating anything. Because phase 2
put `is_writable_now()` inside `get_perms()`, this brings them under the
check-out model at the same time: a claim held by another user now blocks
parameter edits exactly as it blocks an attribute edit. That closes a real
hole in the model rather than a merely theoretical one — parameters are the
bulk of engineering content (§3.5), so a claim that did not cover them would
not have been worth much.

**Interaction with the §3.7 queue.** These handlers can now refuse, so a
reply is no longer by itself a confirmation, and the queue had to learn the
difference: a refusal is *settled* rather than retried (the user will not
acquire the permission by trying again, and an entry that can never succeed
would replay on every sync forever) but it is **reported**, because the local
deletion is about to be undone by the next `get_parmz()` pulling the
parameter back. That undo is correct — the server is authoritative — but it
must not be silent, which is the same principle as §3.4.

Refusals are reported on the live path too, not only the queued one. A
connected user whose deletion is refused has already had it applied to the
local cache, and would otherwise watch it silently revert at the next sync.

Also fixed in passing: `add_de()`/`del_de()` never stamped `state['dez_dts']`,
unlike their parameter counterparts and `set_data_elements()`. Note the dts
values are currently written but never read on the client, so this was latent
rather than active.

Tests: `pangalactic.vger/pangalactic/vger/test/test_parm_auth.py`, 8 cases,
asserting on the *caches* rather than the return message — a handler that
refused in its reply while still mutating the cache would be the same bug
wearing a disguise. 6 of the 8 fail against the pre-fix code; the 2 that pass
are the authorized-path cases, which must pass both before and after.

---

### 3.9 Files, models and documents — as built (2026-08-28..29)

Three rpcs created objects **on the server** that nothing about them required
there: `add_update_model()`, `add_component_file()` and `add_update_doc()`.
Attaching a file to a product, transferring an exported CAD file *set*, and
attaching a document were therefore the only parts of an import that needed a
connection — everything else is built locally and syncs later. All three now
build their objects on the client and are not called. They remain registered
for older clients.

The rule that governs it: **a `RepresentationFile` reaches the repository only
together with its bytes.** A file object without its file is not a degraded
version of the thing, it is a false statement to every other client. So the
bytes are copied into the local vault when the object is made, pushed *before*
the objects (`push_staged_files()` sits ahead of
`sync_user_created_objs_to_repo()` in the chain and the chain waits on it),
and if an upload fails the object is held back for the next sync.

**Held back on both paths, which took two goes.** The immediate one refuses
from the start: `save_new_file_objects()` does not send the objects unless
the upload reported success. The sync did not — it pushed everything in
`created_objects` regardless, so a failed upload followed by a sync produced
exactly the state the rule forbids. `push_staged_files()` now records which
files the repository asked for and did not get, and
`sync_user_created_objs_to_repo()` leaves those oids out of what it offers.

Leaving the oid out is the whole mechanism, and it has to be: the repository
is then told nothing about the object, so it appears in none of the sync's
lists and nothing happens to it. Sending it and filtering later is not an
option — `on_sync_result()` *deletes* a local-only object it cannot
attribute. The retry at the next sync is what repairs it, and by then
`missing_vault_files()` will ask for the bytes again.

**No queue of pending uploads.** The local vault is the record of what this
machine has; `vger.missing_vault_files()` is the record of what the repository
lacks. A queue would be a third record able to disagree with both — and asking
*repairs* history rather than merely avoiding a repeat, so a file whose upload
failed long ago goes up at the next sync. See
`pangalactic.core.digital_files` and NOTES_ON_STEP_IMPORT.md §3c.

#### Who may fetch a file (2026-08-29)

`vger.download_chunk()` checked **nothing** — not even that the caller was a
known user, which `upload_chunk()` has always done. An oid was sufficient to
fetch the bytes it named. In practice that took a deliberately driven WAMP
call rather than anything a user could click, and the oid alone reveals only
a file name, so it was never a leak in normal operation; it is fixed because
the barrier should be permission rather than intent.

`access.may_fetch_file()` decides it, and it asks `get_perms()` about the
object the file represents — "authorization is the model's, since that is
what gains a file", as `add_component_file()` puts it. It must not ask about
the *file*: `RepresentationFile` is in `access.modifiables`, which grants
every user view/modify/delete, so that gate would authorize everybody.

| subject | member of the owner | outsider |
|---|---|---|
| model of a cloaked assembly | yes | no |
| model of a public library product | yes | yes |
| file representing nothing | no | no |

A global admin may fetch anything. Component files inherit their project's
Model — `new_component_file()` gives a component's own Model the
*referencing* model's owner — so a member of the importing project can always
fetch the whole set.

#### The permissions hole this exposed

The gate as first written was correct in form and broken in fact, because
`get_perms()` had nothing to say about a Model. `Model` and `Document` are
`Product` subclasses but not `HardwareProduct`s, and the Product branch
handled only `HardwareProduct` — so a cloaked one matched nothing, fell
through to `[7]`, and answered the empty set. **No member of a project had
even `view` on their own project's models and documents**; only the creator,
by an earlier branch, and a global admin. Nothing depended on that until a
download gate asked, and then a STEP import synced its products to the other
members and its files reached none of them (author, observed 2026-08-29).

Fixed where it belongs rather than routed around (author's rule): a Product
that is not a HardwareProduct now has an `else` branch granting `view`,
`add docs` and `add models` to **any user with a role in the organization
that owns it**. Product type has nothing to say about a model or a document —
the discipline logic is about who may engineer a subsystem — so ownership
decides. `modify` and `delete` are deliberately not granted: the creator
keeps them by the earlier branch, and changing another user's model is not
implied by membership of the project.

An interim fix reimplemented the rule inside `may_fetch_file()` in terms of
`is_cloaked()` and a role lookup. That is gone; the function defers to
`get_perms()`, so there is one definition of who may see an object and the
bytes follow it.

Two test traps let the defect ship, and both are still in the test data.
Every `Person` in `create_test_users()` has a role in H2G2, so what the tests
took for an outsider was a member with an unmatching product type; and the
member they tested with was the local user, who is the *creator* of
everything a test makes and passes by a branch that has nothing to do with
the project. `test_digital_files.py` now creates a Person with no role at all
and uses `buckaroo`, an ordinary member who created nothing.

One client consequence had to be handled with it. `on_chunk_download_failure`
returns None, which tells twisted the failure is handled, so the success
callback chained after it runs anyway — and `on_download_open_success()`
then unpacked that None, raising `TypeError` in the reactor. Harmless while
the only failures were transport ones; a refusal fails *every* chunk. The
completion callbacks now consult `failed_chunks` and report the failure
instead.

#### Fetching the bytes: three routes in, not two

A `RepresentationFile` is a record of a file, not the file, so a client
fetches the ones its viewer can render as they arrive
(`queue_viewable_files()`). That was hooked into `load_serialized_objects()`
and its `force_` twin, "which between them are where every incoming batch
lands". They are where every **sync** lands. A third route exists:
`on_received_objects()`, which handles the `new` and `modified` pubsub
messages — how a client that is *already connected* learns of another user's
import. It deserializes directly, deliberately (`load_serialized_objects()`
there caused ordering problems), and so never queued anything.

So a connected client received the products, the components and the file's
record, and never the file (author, observed 2026-08-29, importing on one
client with a second connected). A client that had been offline and synced
got the file, which is why this was not seen earlier.

**"Already in the vault" now means the right length, not merely present.** A
failed fetch leaves a short file, and `download_chunk()` answers an empty
chunk for a file whose bytes never reached the repository — so testing
existence let one failed fetch poison the cache permanently: the empty file
sat there and every later attempt skipped it. `is_staged()` is the test, the
same one the upload side uses. With retries now possible, `download_file()`
also clears the vault file before requesting chunks, since they are appended
as they arrive and a second attempt would otherwise add to the first. That is
the download counterpart of `upload_chunk()` truncating at chunk 0, done at
the start of the transfer rather than on chunk 0 because the chunks are
requested all at once and need not complete in order.

#### The DocumentReference problem, and why it is a special case

A document is three objects: `Document`, `RepresentationFile`, and the
`DocumentReference` that attaches it to something. The first two are
`Modelable`s and sync like anything else. The third cannot:

- It is an `Identifiable`, so it has **no `creator`** — and
  `sync_user_created_objs_to_repo()` pushes `local_user.created_objects`,
  which is the inverse of `creator`. It can never appear there.
- **It cannot be made a `Modelable`**, which is what was done for the
  placement classes at schema 3.6.0 for exactly this reason. `related_item`
  points at `Modelable`, which would become its own superclass, and
  sqlalchemy's joined table inheritance cannot then tell that foreign key
  from the inheritance one. Verified by execution on 2026-08-29 rather than
  read off the warning in `registry.py`: the orb does not start —
  `AmbiguousForeignKeysError: Can't determine the inherit condition between
  inherited table 'modelable_' and inheriting table 'document_reference_'`.
- **It must not simply be added to the sync's oid list.** `on_sync_result()`
  *deletes* a local-only object with no creator, on the reasoning that the
  repository must have deleted it. A `DocumentReference` listed there would
  be destroyed on the first sync after it was made. This is the trap worth
  remembering: the obvious fix is destructive.

So it travels as a **dependent of its Document**. `push_document_references()`
finds it by way of the Document (which has a creator), asks
`vger.get_mod_dts()` which references the repository already has, and sends
the missing ones together with their Documents — `DESERIALIZATION_ORDER` puts
`Document` first, and re-sending one the repository has costs nothing, since
it comes back "unmodified" and is not republished. `DocumentReference` is in
`access.modifiables`, which is also the only way `vger.save()` will accept
one: it authorizes a new object by "the caller is its creator", and this class
has none.

---

## 4. Suggested sequencing

1. **Decide 3.1** — the offline permission model. Everything else depends
   on it, and the current behaviour cannot be corrected without it.
2. **Stop silent discards (3.4, minimum form)** — make the 1441 filter
   report what it drops. Small, independent of 3.1, and immediately
   improves trust in what the app is doing.
3. **Deletion queue (3.2)** — self-contained, and closes the one basic
   operation that has no path today.
4. **Full reconciliation reporting (3.4)** — once 1-3 give it something
   meaningful to report.
5. **Conflict policy (3.3)** — the largest piece, and the one most worth
   informing with real usage data from 1-4.

## 5. Live validation against marvin.pangalactic.us — results

All three scenarios were run against the live test server (port 443,
self-signed cert) with the two test users, using the headless GUI harness.
Results below are observed, not inferred.

### A. Offline edit without rights → reconnect

zaphod (roles: systems_engineer on H2G2 and DSM, propulsion_engineer)
modified an object he cannot modify — `FDValve-0000866`, owned by PGANA,
one of **428** such objects in his local db — and pushed it via `vger.save`:

```
new_obj_dts  {}
mod_obj_dts  {}
unauth       ['FDValve-0000866']
no_owners    []
```

The repository refused it cleanly and nothing changed server-side, exactly
as predicted. **But note what the server returned**: it names the refused
object in `unauth`. The information needed for reconciliation reporting is
already on the wire — see the new finding in 3.4 below. Layer 3 is
therefore considerably cheaper to build than this note originally assumed.

### B. Offline delete of one's own object → reconnect (read-only probe)

Asked the server what it returns when a client reports every H2G2 oid
*except* one, simulating a client that deleted that object while offline:

```
server reports 63 objects for H2G2 when client sends {}
simulated offline-deleted object: Box-0002203 (HardwareProduct)
client now reports 62 oids (victim omitted)
server returned 1 object(s)  ->  the omitted object
```

Confirmed: the deletion is silently undone. The server returns precisely
the object the client had deleted, and the client deserializes it back.

### C. Stale (offline) edit vs. a newer server copy

On `CommSys-0001284` (`test:twanger`), which zaphod *can* modify:

| step | mod_datetime | accepted? |
|---|---|---|
| current edit | now | **yes** |
| stale edit | now − 1 hour | **no** — silently ignored |
| restore original | now | yes |

**This is the most consequential result for the offline paradigm.** The
conflict policy is not last-write-wins; it is *newer-timestamp-wins, older
silently dropped* (`deserialize` classifies a same-or-earlier
`mod_datetime` as "unmodified" and skips it). Translated into offline
terms: a user goes offline and edits an object at T1; someone else edits
the same object at T2 > T1; on reconnect the offline user's edit is
**discarded without a trace**.

Worse than the unauthorized case: a stale edit does not appear in
`unauth` — it was perfectly authorized — and it is absent from
`mod_obj_dts` only by omission. There is no field in the `vger.save`
response that reports it, and no client code that looks for it. The user's
work simply evaporates.

This makes 3.3 (conflict policy) more urgent than its position in the
sequencing suggests: today, the longer a user stays offline, the higher
the chance their work is silently lost on return.

*Server state was left clean:* the only mutations were to
`CommSys-0001284`'s description, restored to
`'Twanger, Magic, Heavy-Duty'` and verified by reading it back through a
second session logged in as buckaroo.

## 6. Original validation plan (now executed — see section 5)

A test server is available at `marvin.pangalactic.us` (port 443,
self-signed cert, `marvin_server_cert.pem`), and the headless GUI harness
can drive real clients, including two users with separate keys
(`zaphod.key`, `buckaroo.key`). That combination makes the following
directly testable rather than reasoned about:

- Disconnect → edit an object the user has no rights to → reconnect, and
  observe exactly what the user sees (expected today: the edit is dropped
  at the 1441 filter, silently, and persists locally).
- Disconnect → delete one's *own* object → reconnect (expected today: the
  object returns, with no explanation).
- Two clients editing the same object across a disconnect, to characterise
  the current last-write-wins behaviour concretely before choosing a
  conflict policy.

Doing these against the live server first would put real observed
behaviour behind each decision above, rather than inference from the code.
