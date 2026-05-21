"""RadAgent 状态查看工具

用法:
  python -m radagent.status           # 查看当前运行状态
  python -m radagent.status --watch    # 持续监控（每 5 秒刷新）
  python -m radagent.status --json     # JSON 格式输出
"""

import sys
import time


def main():
    from radagent.log import get_status, print_status

    if "--json" in sys.argv:
        import json
        print(json.dumps(get_status(), ensure_ascii=False, indent=2))
        return

    if "--watch" in sys.argv:
        try:
            while True:
                # 清屏 + 打印状态
                print("\033[2J\033[H", end="")
                print_status()
                print("\n(Ctrl+C 退出监控)")
                time.sleep(5)
        except KeyboardInterrupt:
            pass
        return

    print_status()


if __name__ == "__main__":
    main()
