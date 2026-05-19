"""
LangGraph 最小可运行示例
- 带工具的 ReAct Agent
- 用 DeepSeek API（OpenAI 兼容接口）
- 运行: python demo_langgraph.py
"""

import os
import json
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import HumanMessage, SystemMessage


# ── 1. 模型 ──────────────────────────────────────────────
llm = ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com",
    api_key=os.environ["DEEPSEEK_API_KEY"],
    temperature=0,
)

# ── 2. 工具 ──────────────────────────────────────────────
@tool
def add(a: int, b: int) -> int:
    """两数相加"""
    print("get_tool_input: ", a, b)
    return a + b


@tool
def multiply(a: int, b: int) -> int:
    """两数相乘"""
    print("get_tool_input: ", a, b)
    return a * b


@tool
def get_weather(city: str) -> str:
    """查询城市天气（模拟）"""
    data = {"北京": "晴 25°C", "上海": "多云 22°C", "深圳": "阵雨 28°C"}
    print("get_tool_input: ", city)
    return data.get(city, f"{city}: 暂无数据")


tools = [add, multiply, get_weather]
llm_with_tools = llm.bind_tools(tools)


# ── 3. 构建图 ────────────────────────────────────────────
def chatbot(state: MessagesState):
    system = SystemMessage(content="你是一个助手，可以用工具计算或查天气。用中文回答。")
    response = llm_with_tools.invoke([system] + state["messages"])
    print(f"Chatbot 收到消息，生成回复: {response.content}")
    return {"messages": [response]}


builder = StateGraph(MessagesState)

# 节点
builder.add_node("chatbot", chatbot)
builder.add_node("tools", ToolNode(tools))

# 边
builder.add_edge(START, "chatbot")
builder.add_conditional_edges("chatbot", tools_condition)  # 有工具调用→tools，无→END
builder.add_edge("tools", "chatbot")  # 工具结果返回 chatbot

graph = builder.compile()


# ── 4. 运行 ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # 用法: python3 demo_langgraph.py "你的问题"
        question = " ".join(sys.argv[1:])
        result = graph.invoke({"messages": [HumanMessage(content=question)]})
        print(result["messages"][-1].content)
    else:
        # 交互式：输入问题，回车发送，Ctrl+C 退出
        print("LangGraph Agent（输入问题回车发送，Ctrl+C 退出）")
        print("-" * 60)
        try:
            while True:
                question = input("\n你: ").strip()
                if not question:
                    continue
                result = graph.invoke({"messages": [HumanMessage(content=question)]})
                print(f"\nAI: {result['messages']}")
        except (KeyboardInterrupt, EOFError):
            print("\n再见！")
1