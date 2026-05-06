"""
JayClaw 中文开发者工具演示
===========================
演示三个面向中文开发者的特色工具：
  1. search_zhihu    - 搜索知乎技术问答
  2. translate_to_english - 中英翻译（代码注释用）
  3. check_pinyin_naming  - 检测拼音变量名

运行前请确保已安装依赖：
  pip install jay-agent-tools[web]
"""

import asyncio

from jay_agent_tools.web.handlers import (
    handle_check_pinyin_naming,
    handle_search_zhihu,
    handle_translate_to_english,
)


async def demo_search_zhihu() -> None:
    print("\n" + "=" * 60)
    print("工具 1: search_zhihu — 搜索知乎技术问答")
    print("=" * 60)
    result = await handle_search_zhihu({"query": "Python asyncio 最佳实践"})
    if result.ok:
        print(result.data)
    else:
        print(f"[错误] {result.error}")


async def demo_translate() -> None:
    print("\n" + "=" * 60)
    print("工具 2: translate_to_english — 中英翻译")
    print("=" * 60)
    samples = [
        "用户认证模块",
        "获取数据库连接池",
        "处理异常并记录日志",
    ]
    for text in samples:
        result = await handle_translate_to_english({"text": text})
        if result.ok:
            print(result.data)
        else:
            print(f"[错误] {result.error}")
        print()


async def demo_pinyin_check() -> None:
    print("\n" + "=" * 60)
    print("工具 3: check_pinyin_naming — 检测拼音变量名")
    print("=" * 60)

    # 典型的拼音命名代码示例
    sample_code = """
def denglu(yonghu, mima):
    \"\"\"用户登录函数\"\"\"
    if not yonghu or not mima:
        return {"zhuangtai": "cuowu", "xinxi": "参数不能为空"}
    jieguo = chaxun_shujuku(yonghu, mima)
    return {"zhuangtai": "chenggong", "shuju": jieguo}

class YonghuMoxing:
    def __init__(self, yonghuming, mima, jiaose="putong"):
        self.yonghuming = yonghuming
        self.mima = mima
        self.jiaose = jiaose
        self.quanxian = []
"""
    result = await handle_check_pinyin_naming({"code": sample_code, "language": "python"})
    if result.ok:
        print(result.data)
    else:
        print(f"[错误] {result.error}")

    print("\n--- 检测规范代码（应无警告）---")
    clean_code = """
def login(username: str, password: str) -> dict:
    if not username or not password:
        return {"status": "error", "message": "params required"}
    result = query_database(username, password)
    return {"status": "ok", "data": result}
"""
    result2 = await handle_check_pinyin_naming({"code": clean_code})
    if result2.ok:
        print(result2.data)


async def main() -> None:
    print("JayClaw 中文开发者工具演示")
    print("Chinese Developer Tools Demo")

    await demo_search_zhihu()
    await demo_translate()
    await demo_pinyin_check()

    print("\n" + "=" * 60)
    print("演示完成！这些工具可通过 jay-agent-tools 集成到任何 Agent 中。")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
