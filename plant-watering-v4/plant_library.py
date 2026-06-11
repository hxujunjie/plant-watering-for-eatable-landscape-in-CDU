"""
植物库数据层：20种预设植物 + 别名匹配逻辑。
"""

PLANT_CATEGORIES = ['观叶', '多肉', '花卉', '蔬果']

PLANT_LIBRARY = [
    # 观叶类 (5种)
    {'id': 1, 'name': '绿萝', 'aliases': ['绿萝', '黄金葛', '魔鬼藤', '绿萝花'], 'category': '观叶', 'care_tip': '耐阴耐旱，新手友好', 'description': '号称"生命之藤"的室内经典', 'silhouette_path': '/static/img/plants/silhouettes/green_lu.svg', 'illustration_path': '/static/img/plants/illustrations/green_lu.svg'},
    {'id': 2, 'name': '吊兰', 'aliases': ['吊兰', '挂兰', '折鹤兰'], 'category': '观叶', 'care_tip': '喜半阴，忌强光直射', 'description': '垂吊生长的空气净化小能手', 'silhouette_path': '/static/img/plants/silhouettes/spider_plant.svg', 'illustration_path': '/static/img/plants/illustrations/spider_plant.svg'},
    {'id': 3, 'name': '龟背竹', 'aliases': ['龟背竹', '龟背芋', '蓬莱蕉'], 'category': '观叶', 'care_tip': '喜温暖湿润，耐阴', 'description': '叶片独特的热带风情植物', 'silhouette_path': '/static/img/plants/silhouettes/monstera.svg', 'illustration_path': '/static/img/plants/illustrations/monstera.svg'},
    {'id': 4, 'name': '琴叶榕', 'aliases': ['琴叶榕', '琴叶橡胶树', '提琴叶榕'], 'category': '观叶', 'care_tip': '喜光但怕暴晒，浇水见干见湿', 'description': '网红大型观叶植物，叶片如提琴', 'silhouette_path': '/static/img/plants/silhouettes/fiddle_leaf.svg', 'illustration_path': '/static/img/plants/illustrations/fiddle_leaf.svg'},
    {'id': 5, 'name': '散尾葵', 'aliases': ['散尾葵', '黄椰子', '凤尾竹'], 'category': '观叶', 'care_tip': '喜温暖湿润，不耐寒', 'description': '热带风情的客厅装饰植物', 'silhouette_path': '/static/img/plants/silhouettes/areca_palm.svg', 'illustration_path': '/static/img/plants/illustrations/areca_palm.svg'},
    # 多肉类 (5种)
    {'id': 6, 'name': '玉露', 'aliases': ['玉露', '水晶玉露', '草玉露'], 'category': '多肉', 'care_tip': '喜光但怕暴晒，少浇水', 'description': '晶莹剔透的小型多肉', 'silhouette_path': '/static/img/plants/silhouettes/haworthia.svg', 'illustration_path': '/static/img/plants/illustrations/haworthia.svg'},
    {'id': 7, 'name': '石莲花', 'aliases': ['石莲花', '石莲', '多肉莲', '观音莲'], 'category': '多肉', 'care_tip': '喜阳光充足，排水要好', 'description': '莲座状排列的经典多肉', 'silhouette_path': '/static/img/plants/silhouettes/echeveria.svg', 'illustration_path': '/static/img/plants/illustrations/echeveria.svg'},
    {'id': 8, 'name': '芦荟', 'aliases': ['芦荟', '库拉索芦荟', '中国芦荟'], 'category': '多肉', 'care_tip': '喜光耐旱，少浇水', 'description': '实用与观赏兼备的多功能植物', 'silhouette_path': '/static/img/plants/silhouettes/aloe_vera.svg', 'illustration_path': '/static/img/plants/illustrations/aloe_vera.svg'},
    {'id': 9, 'name': '仙人掌', 'aliases': ['仙人掌', '仙人球', '仙人柱'], 'category': '多肉', 'care_tip': '极耐旱，喜阳光', 'description': '沙漠中的生存大师', 'silhouette_path': '/static/img/plants/silhouettes/cactus.svg', 'illustration_path': '/static/img/plants/illustrations/cactus.svg'},
    {'id': 10, 'name': '虎皮兰', 'aliases': ['虎皮兰', '虎尾兰', '虎皮令箭'], 'category': '多肉', 'care_tip': '耐阴耐旱，几乎不用管', 'description': '夜间释放氧气的卧室好伙伴', 'silhouette_path': '/static/img/plants/silhouettes/snake_plant.svg', 'illustration_path': '/static/img/plants/illustrations/snake_plant.svg'},
    # 花卉类 (5种)
    {'id': 11, 'name': '月季', 'aliases': ['月季', '月月红', '玫瑰', '玫瑰月季'], 'category': '花卉', 'care_tip': '喜阳光充足，勤施肥', 'description': '四季开花的花园皇后', 'silhouette_path': '/static/img/plants/silhouettes/chinese_rose.svg', 'illustration_path': '/static/img/plants/illustrations/chinese_rose.svg'},
    {'id': 12, 'name': '茉莉', 'aliases': ['茉莉', '茉莉花', '抹丽'], 'category': '花卉', 'care_tip': '喜阳光充足，喜酸性土壤', 'description': '夏日里最沁人心脾的芬芳', 'silhouette_path': '/static/img/plants/silhouettes/jasmine.svg', 'illustration_path': '/static/img/plants/illustrations/jasmine.svg'},
    {'id': 13, 'name': '栀子', 'aliases': ['栀子', '栀子花', '黄栀子'], 'category': '花卉', 'care_tip': '喜酸性土壤，喜湿润', 'description': '洁白芬芳的南方经典花卉', 'silhouette_path': '/static/img/plants/silhouettes/gardenia.svg', 'illustration_path': '/static/img/plants/illustrations/gardenia.svg'},
    {'id': 14, 'name': '长寿花', 'aliases': ['长寿花', '寿星花', '圣诞伽蓝菜'], 'category': '花卉', 'care_tip': '短日照植物，控制浇水', 'description': '花期超长的室内友好型花卉', 'silhouette_path': '/static/img/plants/silhouettes/kalanchoe.svg', 'illustration_path': '/static/img/plants/illustrations/kalanchoe.svg'},
    {'id': 15, 'name': '蝴蝶兰', 'aliases': ['蝴蝶兰', '蝶兰', 'moth orchid'], 'category': '花卉', 'care_tip': '喜温暖湿润，忌积水', 'description': '高雅脱俗的兰花贵族', 'silhouette_path': '/static/img/plants/silhouettes/phalaenopsis.svg', 'illustration_path': '/static/img/plants/illustrations/phalaenopsis.svg'},
    # 蔬果类 (5种)
    {'id': 16, 'name': '番茄', 'aliases': ['番茄', '西红柿', '圣女果', '小番茄'], 'category': '蔬果', 'care_tip': '喜阳光充足，需支架', 'description': '阳台种菜入门首选', 'silhouette_path': '/static/img/plants/silhouettes/tomato.svg', 'illustration_path': '/static/img/plants/illustrations/tomato.svg'},
    {'id': 17, 'name': '辣椒', 'aliases': ['辣椒', '小米辣', '朝天椒', '青椒'], 'category': '蔬果', 'care_tip': '喜温暖，喜阳光', 'description': '从观叶到结果都有乐趣', 'silhouette_path': '/static/img/plants/silhouettes/pepper.svg', 'illustration_path': '/static/img/plants/illustrations/pepper.svg'},
    {'id': 18, 'name': '薄荷', 'aliases': ['薄荷', '留兰香', '胡椒薄荷'], 'category': '蔬果', 'care_tip': '喜湿润，生长旺盛需修剪', 'description': '清香四溢的厨房好帮手', 'silhouette_path': '/static/img/plants/silhouettes/mint.svg', 'illustration_path': '/static/img/plants/illustrations/mint.svg'},
    {'id': 19, 'name': '罗勒', 'aliases': ['罗勒', '九层塔', 'basil'], 'category': '蔬果', 'care_tip': '喜温暖，需充足阳光', 'description': '意式料理的灵魂香料', 'silhouette_path': '/static/img/plants/silhouettes/basil.svg', 'illustration_path': '/static/img/plants/illustrations/basil.svg'},
    {'id': 20, 'name': '小葱', 'aliases': ['小葱', '葱', '香葱', '大葱'], 'category': '蔬果', 'care_tip': '喜凉爽湿润，容易种植', 'description': '厨房里永远不嫌多的调味品', 'silhouette_path': '/static/img/plants/silhouettes/green_onion.svg', 'illustration_path': '/static/img/plants/illustrations/green_onion.svg'},
]


def match_tag_to_plant(tag_name):
    """通过别名表匹配标签名到植物库。返回植物库条目或None。"""
    if not tag_name:
        return None
    tag_lower = tag_name.strip().lower()
    for plant in PLANT_LIBRARY:
        for alias in plant['aliases']:
            if alias.lower() == tag_lower:
                return plant
    return None


def get_plant_by_id(plant_id):
    """根据ID获取植物库条目。"""
    for plant in PLANT_LIBRARY:
        if plant['id'] == plant_id:
            return plant
    return None


# ========== 培育等级系统 ==========

CULTIVATION_LEVELS = [
    {'level': 1, 'name': '初识', 'min_records': 1, 'min_days': 0},
    {'level': 2, 'name': '熟悉', 'min_records': 5, 'min_days': 0},
    {'level': 3, 'name': '擅长', 'min_records': 15, 'min_days': 30},
    {'level': 4, 'name': '精通', 'min_records': 30, 'min_days': 90},
    {'level': 5, 'name': '大师', 'min_records': 50, 'min_days': 180},
]

CULTIVATION_QUOTES = {
    1: "你和{plant}的初次相遇",
    2: "{plant}开始习惯你的陪伴了",
    3: "你对{plant}的了解，已经超过大多数人",
    4: "如果{plant}会说话，它一定叫你'老朋友'",
    5: "你就是{plant}最棒的培育者，没有之一",
}


def calc_cultivation_level(record_count, care_days):
    """根据记录次数和养护天数计算培育等级。返回等级字典。"""
    level = CULTIVATION_LEVELS[0]
    next_level = None
    for i, lv in enumerate(CULTIVATION_LEVELS):
        if record_count >= lv['min_records'] and care_days >= lv['min_days']:
            level = lv
            if i + 1 < len(CULTIVATION_LEVELS):
                next_level = CULTIVATION_LEVELS[i + 1]
        else:
            break
    # 计算进度
    progress = 1.0
    if next_level:
        rec_progress = (record_count - level['min_records']) / max(1, next_level['min_records'] - level['min_records'])
        day_progress = (care_days - level['min_days']) / max(1, next_level['min_days'] - level['min_days'])
        progress = min(rec_progress, day_progress)
    return {
        'level': level['level'],
        'name': level['name'],
        'progress': max(0, min(1, progress)),
        'record_count': record_count,
        'care_days': care_days,
    }
