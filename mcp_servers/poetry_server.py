"""古诗词查询 MCP Server。

提供古诗词搜索、随机获取、诗人列表等工具。
"""

import random

from mcp.server.fastmcp import FastMCP

# 古诗词数据（至少 10 首）
POEMS = [
    {
        "title": "静夜思",
        "author": "李白",
        "dynasty": "唐",
        "content": "床前明月光，疑是地上霜。举头望明月，低头思故乡。",
    },
    {
        "title": "春晓",
        "author": "孟浩然",
        "dynasty": "唐",
        "content": "春眠不觉晓，处处闻啼鸟。夜来风雨声，花落知多少。",
    },
    {
        "title": "登鹳雀楼",
        "author": "王之涣",
        "dynasty": "唐",
        "content": "白日依山尽，黄河入海流。欲穷千里目，更上一层楼。",
    },
    {
        "title": "望庐山瀑布",
        "author": "李白",
        "dynasty": "唐",
        "content": "日照香炉生紫烟，遥看瀑布挂前川。飞流直下三千尺，疑是银河落九天。",
    },
    {
        "title": "早发白帝城",
        "author": "李白",
        "dynasty": "唐",
        "content": "朝辞白帝彩云间，千里江陵一日还。两岸猿声啼不住，轻舟已过万重山。",
    },
    {
        "title": "咏柳",
        "author": "贺知章",
        "dynasty": "唐",
        "content": "碧玉妆成一树高，万条垂下绿丝绦。不知细叶谁裁出，二月春风似剪刀。",
    },
    {
        "title": "绝句",
        "author": "杜甫",
        "dynasty": "唐",
        "content": "两个黄鹂鸣翠柳，一行白鹭上青天。窗含西岭千秋雪，门泊东吴万里船。",
    },
    {
        "title": "江雪",
        "author": "柳宗元",
        "dynasty": "唐",
        "content": "千山鸟飞绝，万径人踪灭。孤舟蓑笠翁，独钓寒江雪。",
    },
    {
        "title": "清明",
        "author": "杜牧",
        "dynasty": "唐",
        "content": "清明时节雨纷纷，路上行人欲断魂。借问酒家何处有，牧童遥指杏花村。",
    },
    {
        "title": "水调歌头·明月几时有",
        "author": "苏轼",
        "dynasty": "宋",
        "content": "明月几时有？把酒问青天。不知天上宫阙，今夕是何年。我欲乘风归去，又恐琼楼玉宇，高处不胜寒。起舞弄清影，何似在人间。转朱阁，低绮户，照无眠。不应有恨，何事长向别时圆？人有悲欢离合，月有阴晴圆缺，此事古难全。但愿人长久，千里共婵娟。",
    },
    {
        "title": "念奴娇·赤壁怀古",
        "author": "苏轼",
        "dynasty": "宋",
        "content": "大江东去，浪淘尽，千古风流人物。故垒西边，人道是，三国周郎赤壁。乱石穿空，惊涛拍岸，卷起千堆雪。江山如画，一时多少豪杰。遥想公瑾当年，小乔初嫁了，雄姿英发。羽扇纶巾，谈笑间，樯橹灰飞烟灭。故国神游，多情应笑我，早生华发。人生如梦，一尊还酹江月。",
    },
    {
        "title": "如梦令·昨夜雨疏风骤",
        "author": "李清照",
        "dynasty": "宋",
        "content": "昨夜雨疏风骤，浓睡不消残酒。试问卷帘人，却道海棠依旧。知否，知否？应是绿肥红瘦。",
    },
]

# 创建 FastMCP 实例
mcp = FastMCP("poetry-server")

@mcp.tool()
def search_poetry(keyword: str) -> str:
    """搜索包含指定关键词的古诗词。

    在诗词的标题和内容中搜索包含关键词的诗，返回匹配结果。

    Args:
        keyword: 搜索关键词

    Returns:
        匹配的诗词信息，或未找到提示
    """
    if not keyword:
        return "请提供搜索关键词"

    results = []
    for poem in POEMS:
        # 在标题和内容中搜索
        if keyword.lower() in poem["title"].lower() or keyword.lower() in poem["content"].lower():
            results.append(
                f"《{poem['title']}》—— {poem['author']}（{poem['dynasty']}）\n{poem['content']}"
            )

    if not results:
        return "未找到包含该关键词的诗词"

    return "\n\n".join(results)

@mcp.tool()
def random_poetry() -> str:
    """随机返回一首古诗词。

    Returns:
        随机选取的一首诗词，格式：《标题》—— 作者（朝代）\n内容
    """
    poem = random.choice(POEMS)
    return f"《{poem['title']}》—— {poem['author']}（{poem['dynasty']}）\n{poem['content']}"

@mcp.tool()
def list_poets() -> str:
    """获取所有诗人列表。

    Returns:
        所有诗人姓名列表（去重），按朝代分组显示
    """
    # 按朝代分组
    poets_by_dynasty = {}
    for poem in POEMS:
        dynasty = poem["dynasty"]
        author = poem["author"]
        if dynasty not in poets_by_dynasty:
            poets_by_dynasty[dynasty] = set()
        poets_by_dynasty[dynasty].add(author)

    # 格式化输出
    lines = ["诗人列表："]
    for dynasty in sorted(poets_by_dynasty.keys()):
        poets = sorted(poets_by_dynasty[dynasty])
        lines.append(f"\n【{dynasty}】")
        lines.append(", ".join(poets))

    return "\n".join(lines)

if __name__ == "__main__":
    mcp.run(transport="stdio")