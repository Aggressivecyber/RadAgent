"""Memory system frozen dataclasses (DTO)"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class User:
    """用户记录"""
    id: str                          # 用户唯一标识
    display_name: str = ""           # 显示名称
    created_at: str = ""             # 创建时间 ISO8601


@dataclass(frozen=True)
class Project:
    """项目记录"""
    id: str                          # 项目短 ID (uuid[:8])
    user_id: str                     # 所属用户
    title: str = ""                  # 项目标题 (user_input[:80])
    user_input: str = ""             # 用户原始输入
    status: str = "active"           # active | archived
    created_at: str = ""             # 创建时间
    updated_at: str = ""             # 最后更新时间


@dataclass(frozen=True)
class Branch:
    """分支记录（支持参数探索树）"""
    id: str                          # 分支短 ID
    project_id: str                  # 所属项目
    parent_branch_id: str = ""       # 父分支 ID (空=根分支)
    parent_sim_id: str = ""          # 父仿真 ID (从哪个仿真分叉)
    label: str = "main"              # 分支标签
    created_at: str = ""             # 创建时间


@dataclass(frozen=True)
class Simulation:
    """仿真记录"""
    id: str                          # 仿真短 ID
    branch_id: str                   # 所属分支
    session_dir: str = ""            # 日志会话目录
    sim_plan: str = ""               # JSON 仿真方案
    build: str = ""                  # JSON 编译信息
    results: str = ""                # JSON 仿真结果
    report: str = ""                 # JSON 分析报告
    status: str = "running"          # running | completed | failed
    created_at: str = ""             # 创建时间
    finished_at: str = ""            # 完成时间


@dataclass(frozen=True)
class Attempt:
    """L2 会话记忆：门禁评估 + 用户反馈"""
    id: int                          # 自增主键
    simulation_id: str               # 所属仿真
    node: str = ""                   # 节点名 (research_gate / sim_gate / report_gate)
    scores: str = ""                 # JSON 评分
    issues: str = ""                 # JSON 问题列表
    suggestions: str = ""            # JSON 改进建议
    user_action: str = ""            # 用户动作 (continue / modify / cancel)
    user_feedback: str = ""          # 用户反馈文本
    revised_params: str = ""         # JSON 修订参数
    created_at: str = ""             # 创建时间
