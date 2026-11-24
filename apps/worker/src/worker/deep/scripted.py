"""A driver that plays the model from a script: one list of tool calls per turn. Tests and the
$0 end-to-end run use it; the real driver is deep/sdk_driver.py.

Both drivers share the turn loop: ask the harness for the next prompt, let "the model" make its
calls through the harness, repeat until the harness says the run is over. A usage limit pauses.
"""

from dataclasses import dataclass, field

from worker.deep.harness import Harness
from worker.llm.base import UsageLimitReached


@dataclass
class DriverResult:
    stop_reason: str
    turns: int = 0
    prompts: list[str] = field(default_factory=list)


class TurnDriver:
    """The shared loop; a subclass runs one turn of the model."""

    def run(self, harness: Harness) -> DriverResult:
        result = DriverResult(stop_reason="")
        while (prompt := harness.next_prompt()) is not None:
            result.prompts.append(prompt)
            result.turns += 1
            try:
                self.run_turn(harness, prompt)
            except UsageLimitReached as error:
                harness.pause(str(error))
                break
        result.stop_reason = harness.stop_reason
        return result

    def run_turn(self, harness: Harness, prompt: str) -> None:
        raise NotImplementedError


class ScriptedDriver(TurnDriver):
    def __init__(self, turns: list[list[tuple[str, dict]]]):
        self.turns = list(turns)

    def run_turn(self, harness: Harness, prompt: str) -> None:
        calls = self.turns.pop(0) if self.turns else []
        for name, args in calls:
            harness.call(name, args)
            if harness.stop_reason:
                return
