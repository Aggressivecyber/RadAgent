from __future__ import annotations

from typing import Any


async def chat_response_node(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "response_text": (
            "你好，我是 RadAgent，可以帮你进行 Geant4 辐照仿真建模、"
            "参数确认、代码生成、门禁检查和结果整理。"
        ),
        "response_status": "answered",
        "pipeline_terminated": True,
        "current_node": "chat_response",
    }


async def help_response_node(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "response_text": (
            "你可以直接描述仿真任务，例如：建立一个 9 组件硅探测器，"
            "10 MeV proton 入射，输出敏感区能量沉积、氧化层剂量和三维剂量图。\n\n"
            "可用命令：\n"
            "/run <query>  执行仿真管线\n"
            "/step  执行下一阶段\n"
            "/status  查看当前状态\n"
            "/confirm  交互式确认\n"
            "/help  显示帮助"
        ),
        "response_status": "answered",
        "pipeline_terminated": True,
        "current_node": "help_response",
    }


async def status_response_node(state: dict[str, Any]) -> dict[str, Any]:
    job_id = state.get("job_id", "")
    current_phase = state.get("current_phase", "no_active_job")
    if not job_id:
        text = "当前没有正在运行的仿真任务。你可以输入一个建模需求开始。"
    else:
        text = f"当前任务：{job_id}\n当前阶段：{current_phase}"
    return {
        "response_text": text,
        "response_status": "answered",
        "pipeline_terminated": True,
        "current_node": "status_response",
    }


async def capability_response_node(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "response_text": (
            "当前主要支持 Geant4 辐照仿真建模，包括几何、材料、源项、"
            "敏感探测器、scoring、代码生成和门禁检查。TCAD/SPICE 当前为预留能力。"
        ),
        "response_status": "answered",
        "pipeline_terminated": True,
        "current_node": "capability_response",
    }


async def clarification_node(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "response_text": (
            "我还不能确定你是想普通对话，还是要启动仿真建模。"
            "如果要建模，请补充几何结构、材料、粒子源、能量、方向和输出要求。"
        ),
        "response_status": "needs_clarification",
        "pipeline_terminated": True,
        "current_node": "clarification",
    }
