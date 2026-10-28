"""Copy the whole code to a Python Code node in Dify Chatflow.
Input: query (String, sys.query).
Outputs: sql_select (String), sql_log (String).
User text never enters SQL: queries are built solely from predefined categories.
"""

RULES = {
    'pet': ['猫', '狗', '仓鼠', '鹦鹉', '宠物', '喵'],
    'study': ['作业', '学习', '考试', '复习', '论文', '图书馆', '上课', '背单词'],
    'work': ['上班', '老板', '摸鱼', '会议', '打工', '工作', '加班'],
    'digital': ['键盘', '代码', '电脑', '编程', '下载', '手机', '网络', 'wifi', '报错', 'ai'],
    'social': ['朋友', '聊天', '消息', '社交', '群聊', '聚会', '朋友圈'],
    'life': ['起床', '睡觉', '外卖', '吃饭', '洗澡', '拖延', '衣服', '冰箱', '房间'],
}


def main(query: str) -> dict:
    text = (query or '')[:500].lower()
    scored = []
    for category, terms in RULES.items():
        hits = sum(2 if len(term) > 1 else 1 for term in terms if term.lower() in text)
        # One clearly mentioned pet should outrank a generic work/study word.
        if category == 'pet' and any(term in text for term in ('猫', '狗', '仓鼠', '鹦鹉')):
            hits += 3
        if hits > 0:
            scored.append((category, hits))
    # Scores and tie priority favor pet for cat-based comedic trials.
    scored.sort(key=lambda x: (-x[1], list(RULES).index(x[0])))
    categories = [cat for cat, _ in scored[:2]] or ['life', 'social']
    # Everything embedded in the SQL is from this constant, validated list.
    names = ', '.join("'" + cat + "'" for cat in categories)
    order = ' '.join('WHEN ' + "'" + cat + "' THEN " + str(i)
                     for i, cat in enumerate(categories))
    sql_select = (
        'SELECT case_id, category, title, summary, tags, verdict, twist '
        'FROM cyber_case_catalog WHERE category IN (' + names + ') '
        'ORDER BY CASE category ' + order + ' ELSE 99 END, case_id LIMIT 3'
    )
    sql_log = (
        'INSERT INTO cyber_case_plays (case_id) '
        'SELECT case_id FROM cyber_case_catalog WHERE category IN (' + names + ') '
        'ORDER BY CASE category ' + order + ' ELSE 99 END, case_id LIMIT 1'
    )
    return {'sql_select': sql_select, 'sql_log': sql_log, 'category_hint': ','.join(categories)}
