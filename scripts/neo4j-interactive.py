#!/usr/bin/env python3
"""
Neo4j Interactive Graph Analysis for Atlas Core
Provides quick insights and enables ad-hoc Cypher queries
"""

import os
import sys
from neo4j import GraphDatabase

# Connection details
URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD")

class AtlasGraphAnalyzer:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        
    def close(self):
        self.driver.close()
    
    def run_query(self, query, params=None):
        """Run a Cypher query and return results"""
        with self.driver.session() as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]
    
    def top_modules(self, limit=20):
        """Find most connected modules (hubs)"""
        query = """
        MATCH (n:Module)--()
        WITH n, count(*) as degree
        RETURN n.name as module, degree
        ORDER BY degree DESC
        LIMIT $limit
        """
        return self.run_query(query, {"limit": limit})
    
    def modules_importing(self, target_module):
        """Find all modules that import a specific module"""
        query = """
        MATCH (n)-[r:IMPORTS]->(m:Module {name: $target})
        RETURN n.name as importer, r.type as relationship
        ORDER BY n.name
        """
        return self.run_query(query, {"target": target_module})
    
    def blast_radius(self, module_name, hops=3):
        """Calculate blast radius of changing a module"""
        query = """
        MATCH (source:Module {name: $module})
        MATCH path = (source)-[*..${hops}]-(dependent)
        WHERE dependent.type = "Module" OR dependent:Module
        RETURN DISTINCT dependent.name as affected_module, length(path) as distance
        ORDER BY distance
        LIMIT 50
        """
        return self.run_query(query, {"module": module_name, "hops": hops})
    
    def shortest_path(self, start_module, end_module):
        """Find shortest path between two modules"""
        query = """
        MATCH path = shortestPath(
            (a:Module {name: $start})-[*]-(b:Module {name: $end})
        )
        RETURN path
        """
        return self.run_query(query, {"start": start_module, "end": end_module})
    
    def circular_dependencies(self, limit=10):
        """Find circular dependencies"""
        query = """
        MATCH (a:Module)-[r1:IMPORTS]->(b:Module)-[r2:IMPORTS*]->(a)
        RETURN DISTINCT a.name as module_a, b.name as module_b
        LIMIT $limit
        """
        return self.run_query(query, {"limit": limit})
    
    def orphaned_modules(self, limit=20):
        """Find modules with no dependencies"""
        query = """
        MATCH (n:Module)
        WHERE NOT (n)-[:IMPORTS]->()
        AND NOT ()-[:IMPORTS]->(n)
        RETURN n.name as orphaned_module
        LIMIT $limit
        """
        return self.run_query(query, {"limit": limit})
    
    def inference_pipeline(self):
        """Trace the LLM inference pipeline"""
        query = """
        MATCH (q:Module {name: "QuestionEngine"})-[r1:IMPORTS*]->(i:Module {name: "InferenceHub"})
        MATCH (i)-[r2:IMPORTS*]->(p:Module {name: "Provider"})
        RETURN q.name as start, i.name as hub, p.name as provider
        """
        return self.run_query(query)
    
    def memory_flow(self):
        """Trace the memory/state flow"""
        query = """
        MATCH (s:Module {name: "SessionStateStore"})-[r:IMPORTS*]->(m:Module {name: "MemoryTrunk"})
        MATCH (m)-[r2:IMPORTS*]->(index:Module {name: "SqliteMemoryIndex"})
        RETURN s.name as state, m.name as trunk, index.name as persistence
        """
        return self.run_query(query)

def main():
    if not PASSWORD:
        raise SystemExit("NEO4J_PASSWORD is required")
    analyzer = AtlasGraphAnalyzer(URI, USER, PASSWORD)
    
    try:
        print("=" * 70)
        print("🔍 ATLAS CORE - INTERACTIVE GRAPH ANALYSIS")
        print("=" * 70)
        print()
        
        # Test connection
        print("📡 Testing Neo4j connection...", end=" ")
        try:
            test = analyzer.run_query("MATCH (n) RETURN count(n) as count LIMIT 1")
            print("✅ Connected!")
            print()
        except Exception as e:
            print(f"❌ Failed: {e}")
            sys.exit(1)
        
        # Top modules
        print("📊 TOP 20 MOST CONNECTED MODULES (Hubs)")
        print("-" * 70)
        hubs = analyzer.top_modules(20)
        for i, hub in enumerate(hubs, 1):
            print(f"{i:2}. {hub['module']:<40} ({hub['degree']:3} connections)")
        print()
        
        # Modules importing Orchestrator
        print("🔀 MODULES IMPORTING 'Orchestrator'")
        print("-" * 70)
        orch_importers = analyzer.modules_importing("Orchestrator")
        if orch_importers:
            for imp in orch_importers[:10]:
                print(f"  • {imp['importer']}")
        else:
            print("  (none found)")
        print()
        
        # Blast radius
        print("💥 BLAST RADIUS - CHANGING 'PolicyEngine' (3 hops)")
        print("-" * 70)
        blast = analyzer.blast_radius("PolicyEngine", 3)
        if blast:
            for item in blast[:10]:
                print(f"  • {item['affected_module']:<40} (distance: {item['distance']})")
        else:
            print("  (none found)")
        print()
        
        # Circular dependencies
        print("🔄 CIRCULAR DEPENDENCIES")
        print("-" * 70)
        cycles = analyzer.circular_dependencies(10)
        if cycles:
            for cycle in cycles:
                print(f"  • {cycle['module_a']} ↔ {cycle['module_b']}")
        else:
            print("  ✅ No circular dependencies found!")
        print()
        
        # Orphaned modules
        print("👻 ORPHANED MODULES (No dependencies)")
        print("-" * 70)
        orphans = analyzer.orphaned_modules(20)
        if orphans:
            for orphan in orphans[:10]:
                print(f"  • {orphan['orphaned_module']}")
        else:
            print("  ✅ No orphaned modules found!")
        print()
        
        print("=" * 70)
        print("✨ Analysis complete!")
        print("=" * 70)
        print()
        print("💡 Next steps:")
        print("  1. Open Neo4j Browser: http://localhost:7474")
        print("  2. Use CLAUDE_PROMPT.md to dive deeper with Claude")
        print("  3. Check docs/archive/2026-07-14-knowledge-stack/WORKFLOW_GUIDE.md for more analysis patterns")
        print()
        
    finally:
        analyzer.close()

if __name__ == "__main__":
    main()
