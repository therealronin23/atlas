# 🤖 Claude Prompt - Atlas Core Knowledge Graph Analysis

**Copy this prompt into Claude Code / ChatGPT / Copilot and adapt la parte de [OBJETIVO]**

---

## SYSTEM CONTEXT

I'm working on **atlas_core**, a complex AI runtime project with hundreds of modules, classes, and intricate dependencies. I have a complete knowledge graph generated using Graphify:

- **15,304 nodes** (modules, classes, functions)
- **34,549 edges** (imports, dependencies, relationships)
- **607 communities** (architectural clusters)
- **Neo4j database** running locally with all graph data
- **Obsidian vault** with 15,930 cross-linked markdown files

The graph is fresh (rebuilt 2026-07-14) and covers code structure, not documentation. I want you to understand the architecture deeply and help with [OBJETIVO].

---

## WHAT I WANT YOU TO DO

1. **Read and analyze the GRAPH_REPORT.md** (primary context document)
2. **Identify the main architectural hubs** and their roles
3. **Suggest Cypher queries** to explore specific areas
4. **Help me investigate** [OBJETIVO] using graph-based reasoning

---

## HERE'S THE GRAPH REPORT

(Copy the contents of: cat graphify-out/GRAPH_REPORT.md)

[PASTE FULL GRAPH_REPORT.MD HERE]

---

## KEY ARCHITECTURAL INSIGHTS (From pre-analysis)

**Core Hubs**:
- **Orchestrator**: Central execution coordinator
- **MemoryTrunk**: State and persistence layer
- **TransparencyGateway**: Audit and compliance
- **PolicyEngine**: Rules and governance
- **InferenceHub**: LLM and AI integration
- **BrowserTool / EditorTool**: User-facing interfaces

**Main Data Flows**:
- SessionStateStore → MemoryTrunk → SqliteMemoryIndex → MemoryDistiller → MemoryRecord
- Task → DecisionAction → Verdict → MerkleLogger → TransparencyLog → Witness/Signer
- QuestionEngine → InferenceHub → Provider → LiteLLMEmbedder → KuzuVectorStore

---

## YOUR TASK

Analyze the architecture and help me answer these specific questions:

1. **What are the top 5 most critical modules?** (by connectivity / blast radius)
2. **What's the data flow from user input (BrowserTool) to core execution (Orchestrator)?**
3. **How is the LLM integration (InferenceHub) used across the codebase?**
4. **What are potential circular dependencies or architectural debt?**
5. **[ADD YOUR CUSTOM QUESTION HERE]**

---

## ACCESS TO GRAPH DATA

You have access to these tools:

### Neo4j Browser (Interactive)
- URL: http://localhost:7474
- Login: neo4j / atlasneo4j
- Use Cypher queries to explore the graph

### Recommended Cypher Queries to Start

```cypher
-- Find the most connected modules (hubs)
MATCH (n:Module)
WITH n, size((n)-[]-()) as degree
RETURN n.name as module, degree
ORDER BY degree DESC
LIMIT 20
```

```cypher
-- Find what depends on "Orchestrator"
MATCH (n)-[r:IMPORTS]->(m:Module {name: "Orchestrator"})
RETURN n.name as dependent
ORDER BY n.name
```

```cypher
-- Find the blast radius of changing "PolicyEngine"
MATCH (source:Module {name: "PolicyEngine"})
MATCH path = (source)-[*..3]-(dependent)
WHERE dependent.type = "Module"
RETURN DISTINCT dependent.name as affected, length(path) as distance
ORDER BY distance
```

---

## WHAT I NEED FROM YOU

1. A **summary of the main architectural patterns** you observe
2. **Key dependencies and relationships** to understand
3. **Potential areas of technical debt** or complexity
4. **Cypher queries** that would help investigate specific areas
5. **[YOUR CUSTOM REQUEST]**

---

## ADDITIONAL RESOURCES

- **Obsidian Vault**: `~/proyectos/atlas-core/graphify-vault/` (15,930 files with cross-links)
- **Full Cypher Export**: `graphify-out/cypher.txt` (8.4MB of Neo4j import data)
- **Graph JSON**: `graphify-out/graph.json` (19MB raw graph structure)
- **Agents Guide**: `AGENTS.md` (my project's architecture guide)
- **Workflow Guide**: `WORKFLOW_GUIDE.md` (how to use the knowledge stack)

---

## GROUND RULES

- **Use the graph first**: Analyze connectivity patterns, module relationships, and data flows
- **Ground claims in data**: If you claim something, back it up with a Cypher query or graph analysis
- **Avoid hallucination**: If something isn't in the graph, say "I don't see this in the graph"
- **Think in layers**: User → Interface → Execution → Storage → Audit
- **Propose, don't assume**: If you see a pattern, suggest a Cypher query to verify it

---

## STARTING NOW

Ready? Let's go:

**First**, analyze the GRAPH_REPORT.md I pasted above and give me:
1. Top 3 most important modules (justify with graph metrics)
2. Top 3 architectural questions I should ask next
3. One Cypher query that would reveal something interesting about the architecture

Then we'll dive into **[OBJETIVO]** together.

---

**Prepared**: 2026-07-14 | **Graph Freshness**: Commit 5ee77361 | **Nodes**: 15,304 | **Edges**: 34,549
