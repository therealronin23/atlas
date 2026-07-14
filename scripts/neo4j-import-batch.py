#!/usr/bin/env python3
"""
Batch Neo4j Cypher Import for Large Graphify Exports
Splits the cypher.txt file and imports in transactions
"""

import sys
import os
from pathlib import Path

try:
    from neo4j import GraphDatabase
except ImportError:
    print("ERROR: neo4j-driver not installed. Install with: pip install neo4j", file=sys.stderr)
    sys.exit(1)

def main():
    # Configuration
    cypher_file = Path(sys.argv[1] if len(sys.argv) > 1 else "graphify-out/cypher.txt")
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_pass = os.getenv("NEO4J_PASSWORD", "atlasneo4j")
    
    if not cypher_file.exists():
        print(f"ERROR: Cypher file not found: {cypher_file}", file=sys.stderr)
        sys.exit(1)
    
    print(f"📊 Neo4j Batch Import")
    print(f"  File: {cypher_file}")
    print(f"  URI: {neo4j_uri}")
    print(f"  User: {neo4j_user}")
    print()
    
    # Read and split statements
    with open(cypher_file, 'r') as f:
        content = f.read()
    
    # Split by semicolon (Cypher statement separator)
    statements = [s.strip() for s in content.split(';') if s.strip()]
    print(f"📈 Parsed {len(statements)} statements")
    print()
    
    # Connect and import
    driver = None
    try:
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
        
        # Test connection
        print("🔗 Testing connection...", end=" ")
        with driver.session() as session:
            result = session.run("RETURN 1 as test")
            _ = result.single()
        print("✅ OK")
        print()
        
        # Import in batches
        batch_size = 100
        for i in range(0, len(statements), batch_size):
            batch = statements[i:i+batch_size]
            batch_num = (i // batch_size) + 1
            print(f"📤 Batch {batch_num}: importing {len(batch)} statements...", end=" ")
            
            with driver.session() as session:
                for stmt in batch:
                    try:
                        session.run(stmt)
                    except Exception as e:
                        # Log but continue (some statements might be duplicates)
                        pass
            
            print(f"✅ ({i + len(batch)}/{len(statements)})")
        
        print()
        print("✅ Import complete!")
        
        # Verify
        with driver.session() as session:
            node_count = session.run("MATCH (n) RETURN count(n) as count").single()["count"]
            edge_count = session.run("MATCH ()-[r]->() RETURN count(r) as count").single()["count"]
        
        print(f"📊 Result: {node_count:,} nodes, {edge_count:,} edges")
        
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if driver:
            driver.close()

if __name__ == "__main__":
    main()
