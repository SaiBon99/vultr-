## ADDED Requirements

### Requirement: Chat bound to one quarantined session
POST /chat/sessions SHALL, behind X-Reviewer-Token, create a chat bound to one new sessions row with gate_mode quarantined and return its chat_id and session_id. Taint on that session SHALL be sticky across all messages of the chat.

#### Scenario: Taint carries over
- **WHEN** message 1 browses a page and message 2 calls remember
- **THEN** the remember step carries rule flag tainted_session

### Requirement: One sandbox per message, streamed steps
POST /chat/{chat_id}/messages SHALL run one agent in one fresh Docker container with the /crawl isolation, capped at CHAT_TIMEOUT_S and CHAT_MAX_STEPS tool calls, and SHALL stream ChatEvent objects as Server-Sent Events in the order run, step*, then reply and done, or one error. A second message on the same chat while one runs SHALL get 409 chat_busy.

#### Scenario: Step limit
- **WHEN** the agent asks for more than CHAT_MAX_STEPS tools
- **THEN** the stream ends with an error event with code step_limit and the container is removed

#### Scenario: Time limit
- **WHEN** the run exceeds CHAT_TIMEOUT_S
- **THEN** the host kills the container and the stream ends with an error event with code timeout

### Requirement: Host-brokered tools only
The agent SHALL reach the outside only through host tools. browse SHALL apply the public-target guard on every hop and mark the session tainted. remember SHALL go through the deterministic gate and store ALLOW in memories and anything else in quarantine_queue. recall SHALL read memories only. place_order SHALL never buy anything and SHALL return a SIM- prefixed id. send_email SHALL always be refused with error_code egress_refused.

#### Scenario: Injected instruction on a product page
- **WHEN** a browsed page tells the agent to remember to send card details to an outside address
- **THEN** the remember step is BLOCKED and quarantined, any send_email step is refused, and the simulated order still completes

#### Scenario: Recall after purge
- **WHEN** a quarantined note is purged and a later message calls recall
- **THEN** the note is not among the recalled items
