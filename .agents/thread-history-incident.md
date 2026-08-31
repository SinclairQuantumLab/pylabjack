# Codex thread-history rendering incident

Observed: 2026-08-29 through 2026-08-30

Scope: local Codex desktop tooling for the long-running pylabjack development
thread. This is not a pylabjack runtime or source defect.

## Outcome

The missing conversation was recovered. The append-only local rollout log
still contained the historical user and assistant messages. The evidence does
not indicate deletion or corruption of the conversation record.

The best-supported cause is a Codex desktop hydration race/defect when this
paginated thread changes between active-writer ownership and a follower or
newly resumed view. Automatic model-context compaction also occurs in this long
thread, but the evidence does not show that compaction deleted UI history.
Compaction and the large paginated history increase the amount of state the
client must reconstruct and may make the rendering defect easier to expose.

## Evidence

- The rollout session declared `history_mode: paginated` and was approximately
  21 MiB during the audit, ninth-largest among 213 local session files.
- Eight top-level `compacted` events were present. Their replacement context
  retained privileged/current user context plus a compaction summary rather
  than every prior assistant message. This is model-context state; the original
  response records remained elsewhere in the same append-only log.
- Direct inspection found the earlier stream-timing, settling, stream-unification,
  lifecycle, and command-response messages in the original response records.
- Codex desktop logged `thread/resume` error `-32600` with the message `already
  has an active writer` twice for this thread. Across the two inspected daily
  desktop logs, no other thread produced that error.
- The first error occurred about twenty seconds before the user's first report
  of missing conversation. Immediately after the failed resume, the client
  requested `thread/turns/list` and five `thread/items/list` pages to hydrate
  the view.
- On a later reopen, the view attached as a follower owned by another client.
  A second failed resume occurred the same day while the renderer was hidden;
  it again fell back to turn/item listing.
- The desktop logs also contain recurring `ResizeObserver loop completed with
  undelivered notifications` errors. They demonstrate renderer pressure but
  are not specific enough to establish that they caused missing messages.
- The installed Windows app reported version `26.818.5229.0`; the relevant
  desktop log reported release `26.818.41509`, and the session metadata
  reported CLI `0.150.0-alpha.12.2`.
- Searches of the available official Codex documentation did not locate a
  documented explanation for this specific active-writer/paginated-hydration
  failure. The diagnosis therefore rests on local session and desktop logs.

Confidence is high that the transcript was not lost, medium-high that the
visible omission came from owner/follower pagination hydration, and low on the
exact internal UI code path because the response payloads and renderer state
are not fully logged.

## Recurrence prevention and response

Repository-side safeguards:

- `thread-checkpoint.md` records the active resume point and recovered durable
  decisions.
- `AGENTS.md` requires updating that checkpoint around material or
  interruptible work and requires log-based recovery when rendered history is
  incomplete.
- `export-codex-thread.ps1` provides a read-only recovery path without copying
  raw logs or privileged/tool records into the repository.

Operational mitigations for the client defect:

1. Avoid switching away from and immediately back to this thread while it has
   an active writer. Wait for the turn to finish or explicitly interrupt it.
2. If history becomes incomplete, do not continue from the partial rendering.
   Let the writer become idle, reopen the thread once, and compare the result
   with the checkpoint.
3. If reopening remains incomplete, export the local user/assistant record and
   continue in a new thread that begins by reading `AGENTS.md` and
   `thread-checkpoint.md`. A new thread is the strongest practical way to avoid
   this thread-specific hydration state.
4. Install a newer Codex desktop build when one is actually offered. Do not
   assume that an update exists merely from the local version numbers.
5. When reporting the product defect, include the two `thread/resume -32600`
   timestamps, the owner/follower transition, the five item-page hydration
   calls, the app/release/CLI versions above, and the fact that the rollout log
   retained the original messages. Do not attach the raw rollout log without
   reviewing it for private data.

## Later recurrence and transfer

At approximately 20:45 America/Chicago on 2026-08-30, after software
provenance and scalar command-response I/O had been implemented, the user
reported another visible-history omission and chose to move development to a
new thread, agent, or computer. The repository recovery helper exported 259
user/assistant message records through that transfer request from the same
append-only rollout log. The recovered record included the provenance design,
the explicit decision to omit branch/head-ref, removal of the remaining legacy
Stream-In compatibility layer, the complete `ReadWrite` design and
implementation discussion, and the final 122-test result.

This recurrence again showed a presentation/rehydration failure rather than
loss of the append-only conversation record. The raw export was kept outside
the repository; its durable decisions and resume state were reconciled into
`thread-checkpoint.md`, the topic-specific documents, and the implementation.
The requested transfer commit is the recommended continuation point.

## Safeguard validation

- Both thread-ID and explicit-session-file modes of
  `export-codex-thread.ps1` were executed against the affected rollout log.
- The initial recovered output contained 215 user/assistant message records;
  the later transfer audit contained 259 through the commit-and-transfer
  request. Both included the known earlier history-loss reports, user
  comment-preservation correction, `eNames()` decision, and non-Stream timing
  principle.
- During the initial incident response, `uv sync --locked` completed and the
  locked device-free suite passed all 66 then-existing tests. At the transfer
  audit, after provenance and `ReadWrite` were implemented, the suite contained
  and passed 122 tests and both package builds succeeded. Pytest emitted one
  cache-directory permission warning. No native-LJM or physical-hardware test
  was run.
