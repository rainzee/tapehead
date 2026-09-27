from tapehead.stream import AsyncStreamEvents


class Head:
    """磁头, 回放磁带得出上下文, 驱动模型并把结果录回磁带"""

    def __init__(self, system_prompt: str, tools: list, skills: list) -> None:
        self._system_prompt = system_prompt
        self._tools = tools
        self._skills = skills

    async def run(
        self, *, session_id: str, allowed_tools: list[str] | None = None, allowed_skills: list[str] | None = None
    ) -> AsyncStreamEvents:
        raise NotImplementedError
