# Sandbox image: both agents, standard library only, non-root.
# Build: infra/scripts/setup_crawl_sandbox.sh (or docker build -t "$CRAWL_SANDBOX_IMAGE" backend/sandbox).
# Containment (network none, read-only root, no caps, limits) is applied at run time by
# backend/app/crawl/runner.py; this image sets only the user and the interpreter.
# The run command picks the agent: crawl_agent.py by default, chat_agent.py for /chat.
FROM python:3.12-slim
COPY crawl_agent.py chat_agent.py /app/
USER 65534:65534
ENTRYPOINT ["python", "-I", "-S"]
CMD ["/app/crawl_agent.py"]
