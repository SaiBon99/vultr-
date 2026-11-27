"""Plan/write code with a model on Vultr Serverless Inference (OpenAI-compatible API)."""

import re

from openai import AsyncOpenAI

FENCED_CODE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.DOTALL)

SYSTEM_PROMPT = (
    "You write a single self-contained Python 3 script that accomplishes the user's goal. "
    "The script runs in an isolated sandbox with no network secrets and no access to the host. "
    "Print the real results to stdout. Return only the script inside one ```python code block."
)


def extract_code(text: str) -> str:
    match = FENCED_CODE.search(text)
    body = match.group(1) if match else text
    return body.strip() + "\n"


class Planner:
    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self.client = client
        self.model = model

    async def write_code(
        self,
        goal: str,
        previous_code: str | None = None,
        previous_error: str | None = None,
    ) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": goal},
        ]
        if previous_code is not None and previous_error is not None:
            messages.append(
                {"role": "assistant", "content": f"```python\n{previous_code}```"}
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Running that script failed with this stderr:\n"
                        f"{previous_error}\n"
                        "Return a corrected full script in one ```python block."
                    ),
                }
            )
        response = await self.client.chat.completions.create(
            model=self.model, messages=messages
        )
        return extract_code(response.choices[0].message.content or "")
