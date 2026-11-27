## 1. Contracts (Coordinator)
- [x] 1.1 openapi.yaml 0.2.1: `/crawl`, tag `crawl`, CrawlRequest/Limits/Sandbox/Usage/Result, 503 `sandbox_busy`
- [x] 1.2 check_contracts.py passes
- [x] 1.3 Add DECISIONS D7 (Docker sandbox for /crawl), D8 (concurrency 2) and update STATE

## 2. Infra
- [x] 2.1 .env.example: CRAWLER_MODEL, CRAWL_MAX_BYTES, CRAWL_SANDBOX_IMAGE, SANDBOX_* caps, S3_REGION
- [x] 2.2 scripts/setup_crawl_sandbox.sh: install Docker, add the service user to the docker group, build the image (idempotent)

## 3. Backend
- [x] 3.1 app/crawl/guard.py: public http(s) target check, injectable resolver
- [x] 3.2 app/crawl/fetch.py: host fetch with per-hop guard, redirect cap, byte cap, content-type check, host log line
- [x] 3.3 app/crawl/model.py: relay to Vultr Serverless Inference, reply parsing (reject rule for over-long output)
- [x] 3.4 app/crawl/runner.py: docker run argv (`--network none`, read-only, tmpfs noexec, cap-drop ALL, no-new-privileges, non-root, memory/swap, cpus, pids, no `-e`, no mounts), kill and remove on timeout, cidfile for the container id
- [x] 3.5 app/crawl/service.py: stdio broker (fetch and model only), concurrency 2, error mapping (422, 502, 503, 504), response assembly
- [x] 3.6 app/routes/crawl.py: POST /crawl with ReviewerAuth; register in main.py
- [x] 3.7 sandbox/Dockerfile, sandbox/crawl_agent.py (stdlib only, broker protocol)
- [x] 3.8 Offline tests through POST /crawl: auth, validation, guard, fetch limits, broker messages, model parsing, error mapping, timeout; containment argv test; Docker-marked live test

## 4. Live proof (VM)
- [ ] 4.1 Request returns sandbox.network=none and a 64-hex container_id
- [ ] 4.2 docker inspect during a run: NetworkMode none, ReadonlyRootfs, CapDrop, User, no mounts, no env secrets
- [ ] 4.3 Journal line and inference_id match the response
- [ ] 4.4 `docker ps -a` shows no crawl containers after the run
- [ ] 4.5 Vultr console usage rises by one request
