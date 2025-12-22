from __future__ import annotations

from npcframework.api import Engine, Session, RuntimeConfig  # ✅ RuntimeConfig comes from library
from npcframework.npcframework_types import EngineConfig, TurnInput
from npcframework.tools.builtin import builtin_toolset

available_tools, tool_handlers = builtin_toolset(allowlist=["time_now", "add"])

npc_dir = r"C:\Users\Nitro\Desktop\NPCFramework\npc\kevin.npc"
model_path = r"C:\Users\Nitro\Desktop\NPCFramework\npcframework\inference\models\gemma-3-4b-it-q4_0.gguf"

engine = Engine(
    EngineConfig(
        backend="llamacpp",
        model_path=model_path,
        n_ctx=8192,
        n_threads=8,
        n_gpu_layers=0,
        temperature=0.7,
        top_p=0.9,
        max_tokens=512,
    )
)

import npcframework
print(npcframework.__file__)  # ✅ confirm which install you're using

runtime_cfg = RuntimeConfig(
    debug_dump_messages_json=True,
    debug_dump_messages_txt=True,
    debug_dump_dir=r"C:\Users\Nitro\Desktop\NPCFramework\.npc\debug",
)

session = Session(engine=engine, npc_dir=npc_dir, runtime_cfg=runtime_cfg)

result = session.run_turn(
    TurnInput(
        user_input="Hey, how are you?",
        available_tools=available_tools,
        tool_handlers=tool_handlers,
    )
)

print(result.npc_name, ">", result.assistant_reply, "| error:", result.error)
