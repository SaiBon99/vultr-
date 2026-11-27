## ADDED Requirements

### Requirement: One-page crawl in a disposable sandbox
POST /crawl SHALL, behind X-Reviewer-Token, run one crawler agent in one fresh Docker container per request with network none, no environment from the host, no mounts, a read-only root filesystem with a noexec tmpfs, a non-root user, all capabilities dropped, no-new-privileges, memory and swap capped at SANDBOX_MAX_MEMORY_MB, SANDBOX_MAX_CPUS CPUs and 64 processes, and SHALL remove the container after every attempt. The response SHALL be a CrawlResult whose sandbox block carries the 64-hex container id, the image's sha256 id, network none and the limits applied. One attempt, no retry. /crawl SHALL NOT write memory.

#### Scenario: Successful run
- **WHEN** a reviewer posts a public http(s) URL
- **THEN** the API returns 200 with title, summary, key_points, final_url, inference_id, usage or null, elapsed_ms and the sandbox block, and the container no longer exists

#### Scenario: Time limit
- **WHEN** the run exceeds SANDBOX_TIMEOUT_S, counted from container start
- **THEN** the host kills and removes the container and returns 504 timeout

#### Scenario: Busy
- **WHEN** 2 runs are in progress and a third request arrives
- **THEN** the API returns 503 sandbox_busy and starts no container

### Requirement: Host broker
The agent SHALL reach the outside only through the host over stdin and stdout, one JSON object per line, asking once for the page fetch and once for the model call. The inference key SHALL stay on the host. Any other, repeated, out-of-order or malformed message SHALL end the run with 502 agent_crash.

#### Scenario: Unknown request
- **WHEN** the agent sends a message type other than fetch, model or result
- **THEN** the run ends with 502 agent_crash and the container is removed

### Requirement: Public-target fetch
The host SHALL fetch only http(s) URLs with a host, without credentials, whose every resolved address is public, checked before the container starts and on every redirect hop, dialing the vetted address. Redirects SHALL be capped at 3, bodies at CRAWL_MAX_BYTES (read stops at the cap), and content SHALL be HTML or text. Each fetch SHALL write a host log line with URL, final URL, status and size.

#### Scenario: Internal target
- **WHEN** the URL or its hostname resolves to a private, loopback, link-local, multicast or reserved address
- **THEN** the API returns 422 unsafe_target and starts no container

#### Scenario: Redirect inward
- **WHEN** a public page redirects to an internal address
- **THEN** the API returns 502 fetch_failed and no request reaches that address

### Requirement: Trusted model reply
The host SHALL call Vultr Serverless Inference with CRAWLER_MODEL, at most 512 output tokens and a system prompt marking page text as untrusted data. A reply SHALL be accepted only as one JSON object (optionally fenced) with title (at most 300 chars), summary (non-empty, at most 3 sentences and 1000 chars) and key_points (at most 5 non-empty strings of at most 300 chars); anything else SHALL be rejected, never truncated.

#### Scenario: Invalid reply
- **WHEN** the model reply is not JSON, misses a field or breaks a limit
- **THEN** the API returns 502 model_output_invalid without the raw reply

#### Scenario: Failed call
- **WHEN** the model call errors, times out or returns no completion id
- **THEN** the API returns 502 inference_failed
