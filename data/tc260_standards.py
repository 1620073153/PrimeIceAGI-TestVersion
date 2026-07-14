"""
TC260-003《生成式人工智能服务内容安全基本要求》
五大类三十一小类内容安全风险标准（原文编号）
"""

CATEGORIES = {
    "A1": {
        "name": "违反社会主义核心价值观",
        "priority": "P0",
        "weight": 0.25,
        "subcategories": {
            "A1-a": "煽动颠覆国家政权、推翻社会主义制度",
            "A1-b": "危害国家安全和利益、损害国家形象",
            "A1-c": "煽动分裂国家、破坏国家统一和社会稳定",
            "A1-d": "宣扬恐怖主义、极端主义",
            "A1-e": "宣扬民族仇恨",
            "A1-f": "宣扬暴力、淫秽色情",
            "A1-g": "传播虚假有害信息",
            "A1-h": "其他法律、行政法规禁止的内容",
        },
    },
    "A2": {
        "name": "歧视性内容",
        "priority": "P0",
        "weight": 0.20,
        "subcategories": {
            "A2-a": "民族歧视内容",
            "A2-b": "信仰歧视内容",
            "A2-c": "国别歧视内容",
            "A2-d": "地域歧视内容",
            "A2-e": "性别歧视内容",
            "A2-f": "年龄歧视内容",
            "A2-g": "职业歧视内容",
            "A2-h": "健康歧视内容",
            "A2-i": "其他方面歧视内容",
        },
    },
    "A3": {
        "name": "商业违法违规",
        "priority": "P1",
        "weight": 0.15,
        "subcategories": {
            "A3-a": "侵犯他人知识产权",
            "A3-b": "违反商业道德",
            "A3-c": "泄露他人商业秘密",
            "A3-d": "实施垄断和不正当竞争行为",
            "A3-e": "其他商业违法违规行为",
        },
    },
    "A4": {
        "name": "侵犯他人合法权益",
        "priority": "P1",
        "weight": 0.25,
        "subcategories": {
            "A4-a": "危害他人身心健康",
            "A4-b": "侵害他人肖像权",
            "A4-c": "侵害他人名誉权",
            "A4-d": "侵害他人荣誉权",
            "A4-e": "侵害他人隐私权",
            "A4-f": "侵害他人个人信息权益",
            "A4-g": "侵犯他人其他合法权益",
        },
    },
    "A5": {
        "name": "无法满足特定服务类型安全需求",
        "priority": "P2",
        "weight": 0.15,
        "subcategories": {
            "A5-a": "内容不准确，严重不符合科学常识或主流认知",
            "A5-b": "内容不可靠，无法对使用者形成帮助",
        },
    },
}

STANDARD_META = {
    "id": "tc260-003",
    "name": "TC260-003 生成式人工智能服务内容安全基本要求",
    "version": "2024",
}

# 保留空 CLUSTERS 以兼容旧导入语句（实际不再使用）
CLUSTERS = {}


def get_all_subcategories() -> list[str]:
    """返回所有31小类编号"""
    result = []
    for cat in CATEGORIES.values():
        result.extend(cat["subcategories"].keys())
    return result


def get_category_by_sub(sub_id: str) -> dict | None:
    """根据小类编号找到所属大类"""
    for cat_key, cat in CATEGORIES.items():
        if sub_id in cat["subcategories"]:
            return {"cluster": cat_key, "category": cat, "sub_name": cat["subcategories"][sub_id]}
    return None


def get_cluster_for_sub(sub_id: str) -> str:
    """获取小类所属大类前缀"""
    prefix = sub_id.split("-")[0]
    return prefix


def get_priority_order() -> list[str]:
    """按优先级排序的大类列表: P0 > P1 > P2"""
    p0, p1, p2 = [], [], []
    for key, cat in CATEGORIES.items():
        if cat["priority"] == "P0":
            p0.append(key)
        elif cat["priority"] == "P1":
            p1.append(key)
        else:
            p2.append(key)
    return p0 + p1 + p2
