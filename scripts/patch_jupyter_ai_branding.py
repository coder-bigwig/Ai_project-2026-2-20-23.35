from __future__ import annotations

import re
import sys
from pathlib import Path


PERSONA_NAME = "福州理工学院AI助手"
AGENT_AVATAR_ROUTE = "api/ai/static/jupyternaut.svg"


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"未找到可替换片段: {label}")
    return text.replace(old, new, 1)


def _replace_regex(text: str, pattern: str, repl: str, label: str) -> str:
    updated, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"正则替换失败({label})，匹配次数={count}")
    return updated


def patch_persona_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = _replace_regex(
        text,
        r'JupyternautPersona = Persona\(name=".*?", avatar_route=JUPYTERNAUT_AVATAR_ROUTE\)',
        f'JupyternautPersona = Persona(name="{PERSONA_NAME}", avatar_route=JUPYTERNAUT_AVATAR_ROUTE)',
        "persona-name",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_help_message_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    new_template = '''DEFAULT_HELP_MESSAGE_TEMPLATE = """你好！我是 {persona_name}，你的 AI 编程实训助手。
你可以在下方输入问题，也可以使用这些命令：
{slash_commands_list}

你还可以使用以下命令为问题添加上下文：
{context_commands_list}

Jupyter AI 还支持在 Notebook 中使用魔法命令（magic commands）。
更多说明请查看文档：https://jupyter-ai.readthedocs.io/
"""
'''
    text = _replace_regex(
        text,
        r'DEFAULT_HELP_MESSAGE_TEMPLATE = """[\s\S]*?"""\n',
        new_template,
        "help-message-template",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_system_prompt_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    new_prompt = '''CHAT_SYSTEM_PROMPT = """
你是福州理工学院AI助手（JupyterLab 内的对话助手），负责帮助用户完成编程、数据分析和实验学习任务。
请始终使用简体中文回答，除非用户明确要求使用其他语言。
回答应准确、可执行、教学友好，并尽量结合当前 Notebook / 实验上下文。
你不是语言模型本体，而是构建在 {provider_name} 提供的基础模型（{local_model_id}）之上的应用助手。
你可以使用 Markdown 格式化回答。
如果回答包含代码，必须使用 Markdown 代码块（三个反引号）包裹。
如果回答包含数学公式，请使用 LaTeX 标记并用 LaTeX 定界符包裹。
如果你不确定答案，请明确说明你不知道，不要编造。
以下是你与用户之间的一段友好对话。
""".strip()'''
    text = _replace_regex(
        text,
        r'CHAT_SYSTEM_PROMPT = """[\s\S]*?"""\.strip\(\)',
        new_prompt,
        "chat-system-prompt",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_core_bundle(static_dir: Path) -> None:
    target = None
    marker = 'e.message.client.initials))}else{const t=E.ServerConnection.makeSettings().baseUrl+e.message.persona.avatar_route'
    for p in sorted(static_dir.glob("*.js")):
        text = p.read_text(encoding="utf-8", errors="ignore")
        if marker in text:
            target = p
            break
    if target is None:
        raise RuntimeError("未找到 Jupyter AI 前端 bundle（头像渲染逻辑）")

    text = target.read_text(encoding="utf-8", errors="ignore")
    old_human_branch = (
        'if("human"===e.message.type){const r=null===(t=null==n?void 0:n[e.message.client.username])||void 0===t?void 0:t.color;'
        'l=s().createElement(m.Avatar,{sx:{...o,...r&&{bgcolor:r}}},s().createElement(m.Typography,{sx:{fontSize:"var(--jp-ui-font-size1)",'
        'color:"var(--jp-ui-inverse-font-color1)"}},e.message.client.initials))}else{'
    )
    new_human_branch = (
        f'if("human"===e.message.type){{const r=E.ServerConnection.makeSettings().baseUrl+"{AGENT_AVATAR_ROUTE}";'
        'l=s().createElement(m.Avatar,{sx:{...o,bgcolor:"var(--jp-layout-color-1)"}},s().createElement("img",{src:r}))}else{'
    )
    text = _replace_once(text, old_human_branch, new_human_branch, "core-human-avatar-branch")
    text = text.replace('return"Jupyternaut"', f'return"{PERSONA_NAME}"')
    target.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    persona_path = Path("/opt/conda/lib/python3.11/site-packages/jupyter_ai_magics/models/persona.py")
    extension_path = Path("/opt/conda/lib/python3.11/site-packages/jupyter_ai/extension.py")
    provider_path = Path("/opt/conda/lib/python3.11/site-packages/jupyter_ai_magics/base_provider.py")
    core_static_dir = Path("/opt/conda/share/jupyter/labextensions/@jupyter-ai/core/static")

    for p in [persona_path, extension_path, provider_path]:
        if not p.exists():
            raise FileNotFoundError(str(p))
    if not core_static_dir.exists():
        raise FileNotFoundError(str(core_static_dir))

    patch_persona_file(persona_path)
    patch_help_message_file(extension_path)
    patch_system_prompt_file(provider_path)
    # Keep the official frontend bundle untouched to avoid runtime rendering regressions.
    # Persona name/avatar and server-side Chinese prompts are patched via Python modules/static asset.
    _ = core_static_dir
    print("Jupyter AI branding patch applied.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - image build diagnostics
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
