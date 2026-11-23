def compact_segments(segments):
    fields=('id','start','end','text','alignment_uncertain')
    return [{key:row[key] for key in fields if key in row} for row in segments]


SELECT = '''审阅整段直播转写，选择独立成立、约15秒的连续商品讲解。
优先12–20秒，允许10–25秒；不要凑时长。至少两个具体、不重复的商品事实，
例如材质和穿着感、版型和适用身形、结构细节和用途。价格、优惠券、截单、发货、
重复催单、闲聊不算商品事实。只有一句完整的话仍可能毫无价值，必须淘汰。
整个候选中不得包含价格、折扣、优惠券、凑单、限时、直播当天销量或其他可能过期的促销信息；
若促销和商品讲解相连，只选择可独立成立且完整的商品讲解，不得跨越被删句子拼成连续片段。
不能跨商品，不能依赖前文“这个/那个”的指代，不能截断论点、条件或句子。
特别注意：以“给你们做的是”“所以”“并且”等承接前文的词开头，或缺失所述商品的主体，
应把前面的完整介绍一起保留；若因此超过时长，则拒绝该候选。
转写疑似错误影响核心卖点时拒绝。不能改写转写、编造材质，不要把销售峰值当内容质量。
返回JSON: {"clips": [...], "reason": "整体结论"}，最多6条，完全没合格则clips为空。
每条格式：{"first_id":0,"last_id":1,"kind":"product_explanation","product":"商品名称",
"facts":[{"quote":"入选原文内逐字证据","type":"material"}],
"information_score":4,"completeness_score":4,"filler_ratio":0.1,"complete":true,"reason":"理由"}。
fact类型仅material/fit/construction/detail/wearing/use_case/comparison；分数1–5。
first_id与last_id之间所有句子都会保留，不允许隐藏删句。完整转写如下：
'''

SELECT = SELECT.replace('完整转写如下：', '''务必用 last_id 对应 end 减去 first_id 对应 start 计算真实时长，不能按字数或句数估算。
超过30秒必须缩小到仍完整的独立论点，不能把33秒说成22秒。facts.quote必须逐字连续摘录，不能使用省略号或补入标点。
带alignment_uncertain=true的句子和前后依赖它的内容不得选择。优先15–20秒；保留完整表达可到30秒。
完整转写如下：''')

VISUAL = '''以下是候选连续片段每秒抽样画面和对应转写。审查商品是否与讲解一致、
商品是否清晰出现、是否大量空镜或无关画面。图像按时间顺序排列。
不要从人穿的衣服推断它就是话术中的商品。无法确认商品一致则拒绝。
返回JSON: {"matches_product":true,"complete":true,"product_visible_ratio":0.9,
"empty_ratio":0.0,"reason":"明确的画面证据及限制"}。
ratio按提供的抽样图计算，不声称检查未提供的帧；complete表示证据充分到可以通过。
候选内容：
'''
