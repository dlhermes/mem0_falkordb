UPDATE_GRAPH_PROMPT = """
You are an AI expert specializing in graph memory management and optimization. Your task is to analyze existing graph memories alongside new information, and update the relationships in the memory list to ensure the most accurate, current, and coherent representation of knowledge.

Input:
1. Existing Graph Memories: A list of current graph memories, each containing source, target, and relationship information.
2. New Graph Memory: Fresh information to be integrated into the existing graph structure.

Guidelines:
1. Identification: Use the source and target as primary identifiers when matching existing memories with new information.
2. Conflict Resolution:
   - If new information contradicts an existing memory:
     a) For matching source and target but differing content, update the relationship of the existing memory.
     b) If the new memory provides more recent or accurate information, update the existing memory accordingly.
3. Comprehensive Review: Thoroughly examine each existing graph memory against the new information, updating relationships as necessary. Multiple updates may be required.
4. Consistency: Maintain a uniform and clear style across all memories. Each entry should be concise yet comprehensive.
5. Semantic Coherence: Ensure that updates maintain or improve the overall semantic structure of the graph.
6. Temporal Awareness: If timestamps are available, consider the recency of information when making updates.
7. Relationship Refinement: Look for opportunities to refine relationship descriptions for greater precision or clarity.
8. Redundancy Elimination: Identify and merge any redundant or highly similar relationships that may result from the update.

Memory Format:
source -- RELATIONSHIP -- destination

Task Details:
======= Existing Graph Memories:=======
{existing_memories}

======= New Graph Memory:=======
{new_memories}

Output:
Provide a list of update instructions, each specifying the source, target, and the new relationship to be set. Only include memories that require updates.
"""

EXTRACT_RELATIONS_PROMPT = """

你是一个高级算法，设计用于从文本中提取结构化信息以构建知识图谱。你的目标是捕获全面且准确的信息。请遵循以下关键原则：

1. 仅提取文本中明确陈述的信息。
2. 在提供的实体之间建立关系。
3. 对用户消息中的自指代（如"我"、"我的"等），使用 "USER_ID" 作为源实体。
4. 必须用与输入相同的语言输出所有关系描述。如果输入是中文，关系描述必须用中文。
CUSTOM_PROMPT

关系类型（硬性约束——违反将导致关系被丢弃）：
    - 使用一致、通用且不限时态的关系类型。
    - 示例：优先使用"教授"而非"成为教授"。
    - 关系应仅在用户消息中明确提及的实体之间建立。
    - 【硬性禁止】绝不使用 "related_to"。related_to 是无意义兜底占位符，不是合法关系类型。输出 related_to 的关系将被系统视为无效结果、直接丢弃。
    - 必须从文本中推断出具体语义动词。示例替换对照：
        文本提到"喜欢"→ 用"偏好"；提到"装/放了"→ 用"部署于/部署到"
        提到"修/改了"→ 用"修复了/配置了"；提到"是/归属"→ 用"属于"
        提到"管/看管"→ 用"负责"；提到"用/采用"→ 用"使用"
        提到"做/建了"→ 用"创建"
    - 如果实在无法从文本推断出具体关系动词，宁可跳过该关系对（不输出），也不得使用 related_to。

实体与关系质量约束：
    - 禁止建立自引用关系（source == destination 的关系一律跳过）。
    - 关系的两端必须是完整的、有意义的实体名称。禁止使用碎片词（如"未"、"是"、"阈值"、"了"等不完整的截断词）作为 source 或 destination。
    - 关系描述本身必须是完整的语义短语，不能是单字或碎片。
    - 如果两个实体之间没有明确、可验证的语义关系，不要强行建立关系——宁可跳过该关系对。

实体一致性：
    - 确保关系逻辑一致，与消息上下文相符。
    - 在提取的数据中保持实体命名一致。

努力构建一个连贯且易于理解的知识图谱，通过建立实体之间明确、有意义的关系来贴合用户上下文。

严格遵守这些准则，确保高质量的知识图谱提取。"""

DELETE_RELATIONS_SYSTEM_PROMPT = """
You are a graph memory manager specializing in identifying, managing, and optimizing relationships within graph-based memories. Your primary task is to analyze a list of existing relationships and determine which ones should be deleted based on the new information provided.
Input:
1. Existing Graph Memories: A list of current graph memories, each containing source, relationship, and destination information.
2. New Text: The new information to be integrated into the existing graph structure.
3. Use "USER_ID" as node for any self-references (e.g., "I," "me," "my," etc.) in user messages.

Guidelines:
1. Identification: Use the new information to evaluate existing relationships in the memory graph.
2. Deletion Criteria: Delete a relationship only if it meets at least one of these conditions:
   - Outdated or Inaccurate: The new information is more recent or accurate.
   - Contradictory: The new information conflicts with or negates the existing information.
3. DO NOT DELETE if their is a possibility of same type of relationship but different destination nodes.
4. Comprehensive Analysis:
   - Thoroughly examine each existing relationship against the new information and delete as necessary.
   - Multiple deletions may be required based on the new information.
5. Semantic Integrity:
   - Ensure that deletions maintain or improve the overall semantic structure of the graph.
   - Avoid deleting relationships that are NOT contradictory/outdated to the new information.
6. Temporal Awareness: Prioritize recency when timestamps are available.
7. Necessity Principle: Only DELETE relationships that must be deleted and are contradictory/outdated to the new information to maintain an accurate and coherent memory graph.

Note: DO NOT DELETE if their is a possibility of same type of relationship but different destination nodes. 

For example: 
Existing Memory: alice -- loves_to_eat -- pizza
New Information: Alice also loves to eat burger.

Do not delete in the above example because there is a possibility that Alice loves to eat both pizza and burger.

Memory Format:
source -- relationship -- destination

Provide a list of deletion instructions, each specifying the relationship to be deleted.
"""


def get_delete_messages(existing_memories_string, data, user_id):
    return DELETE_RELATIONS_SYSTEM_PROMPT.replace(
        "USER_ID", user_id
    ), f"Here are the existing memories: {existing_memories_string} \n\n New Information: {data}"
