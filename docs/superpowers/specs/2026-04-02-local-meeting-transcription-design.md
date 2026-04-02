# Local Meeting Transcription App Design

Date: 2026-04-02
Status: Approved for spec review

## 1. Summary

This project is a single-user local macOS webapp for live meeting transcription from system audio. The app runs entirely on the user's machine, captures audio from a configured macOS system-audio source, generates a continuously updating English transcript, and derives live meeting insights during the session.

The v1 product is optimized for one Apple Silicon Mac and one operator. Its primary live experience is insight-first: topic clusters, extracted action items, and extracted decisions are the main dashboard elements, while the transcript remains continuously visible as supporting context. The app also supports manual bookmarks with a note and an attached transcript snippet.

The core product boundary for v1 is:

- local-only execution
- local web UI on localhost
- macOS system audio capture
- English live transcription
- live topic/action/decision extraction
- transcript persistence after the meeting
- no multi-user behavior
- no remote service dependency

## 2. Product goals

### Primary goals

- Provide live meeting transcription from macOS system audio on a local machine.
- Keep average live transcript latency below 2 seconds during normal operation.
- Surface useful live meeting insights without blocking the transcript path.
- Save finalized transcripts locally for later review.
- Keep the first version narrowly scoped and reliable for one user's workflow.

### Non-goals for v1

- Cross-platform support.
- Cloud processing or shared/team deployment.
- Full transcript editing or knowledge-management workflows.
- Guaranteed speaker diarization in the core path.
- General meeting assistant features beyond transcript, insights, and bookmarks.

## 3. User and environment

### Primary user

One operator on one Apple Silicon Mac.

### Assumptions

- The user is willing to perform one-time local audio-routing setup if needed.
- The system-audio source is the primary capture input.
- The default local speech-to-text model family is based on Kyutai STT 1B EN/FR, configured for English in v1.

## 4. System architecture

The system is divided into three clear layers:

### 4.1 Local UI

A browser-based local UI runs on localhost and provides:

- session start and stop controls
- source health and readiness state
- live transcript display
- live topic cluster display
- live action item display
- live decision display
- bookmark creation

### 4.2 Session orchestrator

A local backend process owns the session lifecycle and coordinates:

- session state
- capture start and stop
- transcript accumulation
- bookmark creation
- persistence of finalized transcripts
- live update delivery to the UI
- downstream triggering of insight extraction

### 4.3 Audio and ML pipeline

The audio and ML layer contains two linked but independent processing paths.

#### Transcription path

The transcription path is the fast path. It:

- receives rolling audio from the configured macOS system-audio source
- feeds audio to the local STT engine
- produces live transcript updates
- commits confirmed transcript segments with timestamps

This path is optimized for continuity and low latency.

#### Insight path

The insight path is downstream from transcription. It:

- consumes recent transcript windows rather than raw audio
- produces running topic clusters
- extracts candidate action items
- extracts candidate decisions
- refreshes insight panels independently of transcript updates

This separation ensures that slower insight generation does not block live transcription.

## 5. UX and session workflow

### 5.1 Main workspace

The main session screen uses an insight-first layout:

- top control bar for session state, source status, start/stop, and bookmark creation
- left insight column for topic clusters, action items, and decisions
- right transcript stream for timestamped live transcript updates

### 5.2 Session flow

1. The user opens the local app.
2. The app shows source readiness and session controls.
3. The user starts the session.
4. The app begins capture and live processing.
5. The transcript updates continuously.
6. Insights update in near-real-time with allowed lag behind transcript updates.
7. The user may create bookmarks at any time.
8. The user stops the session.
9. The app finalizes and saves the transcript locally.
10. The saved transcript becomes available for later review and insight regeneration.

### 5.3 UX principles

- Transcript continuity is more important than insight freshness.
- The UI must expose source and model state clearly.
- The UI must distinguish live data, stale data, and failed updates.
- Error states must be actionable.

## 6. Data model

Each session conceptually contains:

- session metadata
- source and capture state history
- timestamped transcript segments
- bookmarks with timestamp, user note, and linked transcript snippet
- derived live insight artifacts
- finalized saved transcript artifact

The transcript is the primary persisted asset for v1. Insight artifacts may be treated as derived data that can be regenerated later from the saved transcript.

## 7. Failure handling

### 7.1 Start-time failures

If the configured system-audio source is unavailable when the user starts a session, the app must:

- prevent session start
- preserve operator confidence by explaining the problem clearly
- present actionable setup guidance

### 7.2 In-session capture failure

If capture is interrupted during a live session, the app must:

- preserve the session record
- show degraded or disconnected source state
- stop adding new transcript text until capture resumes or the user ends the session

### 7.3 Model warmup or slowdown

If the transcription model is warming up or temporarily slow, the app must:

- show model state clearly
- keep the session active
- resume live updates when processing catches up

### 7.4 Insight lag or failure

If insight extraction lags or fails, the app must:

- continue transcript updates
- keep the last known insight state visible
- indicate that insights are delayed or stale

## 8. Persistence

At the end of each meeting, the app saves the finalized transcript locally with timing metadata. The saved transcript becomes the canonical session artifact for later review.

The first version should avoid adding a full post-meeting editor or analysis workspace. It only needs enough stored context to make the transcript reviewable and to allow later regeneration of session insights.

## 9. Testing strategy

### 9.1 Unit tests

Unit coverage should include:

- transcript segment handling
- transcript timing metadata handling
- topic clustering boundaries
- action item extraction formatting
- decision extraction formatting
- bookmark and snippet association behavior

### 9.2 Integration tests

Integration coverage should include:

- session lifecycle behavior
- audio-capture-to-transcript flow
- transcript-to-insight flow
- transcript finalization and save flow

### 9.3 Manual system validation

Manual validation should include:

- macOS system-audio routing setup
- live session run on Apple Silicon
- observed transcript latency against the 2-second target
- degraded-path behavior for unavailable source, interrupted capture, and lagging insights

## 10. EARS requirements

### Scope and deployment

**REQ-001 — Ubiquitous**  
The meeting transcription app SHALL run on a single local macOS machine.

**REQ-002 — Ubiquitous**  
The meeting transcription app SHALL process meeting audio without requiring a remote service.

**REQ-003 — Ubiquitous**  
The meeting transcription app SHALL provide a local web interface for session control and live session monitoring.

### Session lifecycle

**REQ-004 — Event-driven**  
WHEN the user starts a meeting session, the meeting transcription app SHALL create a new local session record.

**REQ-005 — Event-driven**  
WHEN the user stops a meeting session, the meeting transcription app SHALL finalize the active session.

**REQ-006 — State-driven**  
WHILE a meeting session is active, the meeting transcription app SHALL display the current session state to the user.

### Audio capture

**REQ-007 — Event-driven**  
WHEN the user starts a meeting session, the meeting transcription app SHALL begin capturing audio from the configured system-audio source.

**REQ-008 — State-driven**  
WHILE a meeting session is active, the meeting transcription app SHALL display system-audio capture status.

**REQ-009 — Unwanted**  
IF the configured system-audio source is unavailable when the user starts a meeting session, THEN the meeting transcription app SHALL prevent session start.

**REQ-010 — Unwanted**  
IF the meeting transcription app prevents session start, THEN the meeting transcription app SHALL display an actionable error message.

### Live transcription

**REQ-011 — State-driven**  
WHILE a meeting session is active, the meeting transcription app SHALL produce a continuously updating live transcript in English.

**REQ-012 — Event-driven**  
WHEN new transcript text is confirmed, the meeting transcription app SHALL append the text to the session transcript.

**REQ-013 — Event-driven**  
WHEN the meeting transcription app appends transcript text, the meeting transcription app SHALL store timing metadata for that text.

**REQ-014 — State-driven**  
WHILE a meeting session is active, the meeting transcription app SHALL present the live transcript in the local web interface.

**REQ-015 — Ubiquitous**  
The meeting transcription app SHALL maintain average live transcript latency below 2 seconds during normal operation.

### Live topic extraction

**REQ-016 — State-driven**  
WHILE a meeting session is active, the meeting transcription app SHALL generate running topic clusters from recent transcript content.

**REQ-017 — State-driven**  
WHILE a meeting session is active, the meeting transcription app SHALL display current topic clusters in the local web interface.

**REQ-018 — Event-driven**  
WHEN topic-cluster prominence changes, the meeting transcription app SHALL update the displayed topic ordering.

### Live action and decision extraction

**REQ-019 — State-driven**  
WHILE a meeting session is active, the meeting transcription app SHALL extract candidate action items from recent transcript content.

**REQ-020 — State-driven**  
WHILE a meeting session is active, the meeting transcription app SHALL extract candidate decisions from recent transcript content.

**REQ-021 — State-driven**  
WHILE a meeting session is active, the meeting transcription app SHALL display extracted action items in the local web interface.

**REQ-022 — State-driven**  
WHILE a meeting session is active, the meeting transcription app SHALL display extracted decisions in the local web interface.

**REQ-023 — Event-driven**  
WHEN live insight generation lags behind transcript generation, the meeting transcription app SHALL continue updating the transcript without waiting for insight results.

### Bookmarks

**REQ-024 — Event-driven**  
WHEN the user creates a bookmark during an active meeting session, the meeting transcription app SHALL store the bookmark timestamp.

**REQ-025 — Event-driven**  
WHEN the user creates a bookmark during an active meeting session, the meeting transcription app SHALL store the user-entered note.

**REQ-026 — Event-driven**  
WHEN the user creates a bookmark during an active meeting session, the meeting transcription app SHALL associate the bookmark with a transcript snippet from the surrounding session context.

**REQ-027 — State-driven**  
WHILE a meeting session is active, the meeting transcription app SHALL allow the user to create a bookmark from the local web interface.

### Persistence and review

**REQ-028 — Event-driven**  
WHEN a meeting session ends, the meeting transcription app SHALL save the finalized transcript to local disk.

**REQ-029 — Event-driven**  
WHEN the meeting transcription app saves a finalized transcript, the meeting transcription app SHALL preserve session timing metadata in the saved record.

**REQ-030 — Event-driven**  
WHEN a finalized transcript has been saved, the meeting transcription app SHALL make that transcript available for later local review.

**REQ-031 — Event-driven**  
WHEN a finalized transcript is available for later local review, the meeting transcription app SHALL allow session insights to be regenerated from the saved transcript.

### Optional/stretch requirements

**REQ-032 — Optional**  
WHERE speaker separation is enabled, the meeting transcription app SHALL label transcript segments with speaker identifiers.

**REQ-033 — Optional**  
WHERE speaker separation is enabled, the meeting transcription app SHALL omit speaker identifiers for segments below `<MIN_SPEAKER_CONFIDENCE>` confidence.

**REQ-034 — Ubiquitous**  
The meeting transcription app SHALL store all session artifacts under a user-accessible local application data directory.

## 11. Planning notes

The implementation plan should prioritize the following order:

1. session and local app skeleton
2. macOS system-audio capture path
3. live transcription path
4. live session UI with transcript and source state
5. insight extraction path
6. bookmarks and linked transcript snippets
7. transcript persistence and later review/regeneration hooks
8. optional speaker separation only after the core path is stable

The core planning scope should focus on REQ-001 through REQ-031. REQ-032 and REQ-033 are stretch requirements and should not block the first usable version.
