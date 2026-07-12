
import ast
import sys
from pathlib import Path

def build_import_graph(src_dir: Path) -> dict[str, set[str]]:
    """
    Construye el grafo de imports de src/atlas.
    Nodos: módulos atlas.* (ruta relativa convertida a nombre de módulo).
    Aristas: imports entre módulos atlas (import X y from X import Y, incluidos imports dentro de funciones).
    """
    graph: dict[str, set[str]] = {}
    trees: dict[str, ast.Module] = {}

    for file_path in src_dir.rglob('*.py'):
        if file_path.name == '__init__.py':
            continue

        module_name = "atlas." + str(file_path.relative_to(src_dir)).replace('/', '.')[:-3]
        graph[module_name] = set()

        try:
            trees[module_name] = ast.parse(file_path.read_text())
        except Exception as e:
            print(f"Error parsing {file_path}: {e}", file=sys.stderr)

    # Módulos reales descubiertos en el árbol (necesario para distinguir
    # "from atlas import b" -> submódulo atlas.b de "from atlas.x import Y"
    # -> símbolo Y dentro de atlas.x, sin importar de verdad el paquete).
    real_modules = set(trees.keys())

    for module_name, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_module = alias.name
                        if imported_module.startswith("atlas."):
                            graph[module_name].add(imported_module)
                elif isinstance(node, ast.ImportFrom):
                    if node.level > 0:  # Relative import
                        # Calculate absolute path for relative import
                        # This is a simplified approach and might not cover all edge cases
                        # For a full solution, sys.path and importlib would be needed
                        # but the prompt specifies ONLY stdlib (ast, pathlib)
                        parent_module_parts = module_name.split('.')[:-1]
                        for _ in range(node.level - 1):
                            if parent_module_parts:
                                parent_module_parts.pop()

                        if node.module:
                            base_module = ".".join(parent_module_parts + [node.module])
                        else:  # from . import X
                            base_module = ".".join(parent_module_parts)
                    else:  # Absolute import
                        base_module = node.module or ""

                    if not base_module or base_module != "atlas" and not base_module.startswith("atlas."):
                        continue

                    # "from MODULE import NAME": si MODULE.NAME es un
                    # submódulo real, la arista es esa; si no, NAME es un
                    # símbolo (clase/función) y la arista es MODULE.
                    added_submodule = False
                    for alias in node.names:
                        candidate = f"{base_module}.{alias.name}"
                        if candidate in real_modules:
                            graph[module_name].add(candidate)
                            added_submodule = True
                    if not added_submodule:
                        graph[module_name].add(base_module)
    
    # Ensure all imported modules that are part of atlas also exist as keys in the graph
    all_modules = set(graph.keys())
    for imports in graph.values():
        all_modules.update(imports)
    
    for mod in all_modules:
        if mod.startswith("atlas.") and mod not in graph:
            graph[mod] = set()

    return graph

def fan_in(graph: dict[str, set[str]]) -> dict[str, int]:
    """Calcula el fan-in para cada módulo."""
    fan_in_counts: dict[str, int] = {node: 0 for node in graph}
    for node in graph:
        for imported_node in graph[node]:
            if imported_node in fan_in_counts:
                fan_in_counts[imported_node] += 1
    return fan_in_counts

def find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Encuentra ciclos simples en el grafo usando DFS."""
    cycles: list[list[str]] = []
    path: list[str] = []
    visited: set[str] = set()
    recursion_stack: set[str] = set()

    def dfs(node: str) -> None:
        visited.add(node)
        recursion_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, set()):
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in recursion_stack:
                cycle_start_index = path.index(neighbor)
                cycles.append(path[cycle_start_index:] + [neighbor])
        
        path.pop()
        recursion_stack.remove(node)

    for node in graph:
        if node not in visited:
            dfs(node)
    
    return cycles

def main():
    src_dir = Path('src/atlas')
    if not src_dir.is_dir():
        print(f"Error: Directorio '{src_dir}' no encontrado.", file=sys.stderr)
        sys.exit(1)

    import_graph = build_import_graph(src_dir)

    total_nodes = len(import_graph)
    total_edges = sum(len(imports) for imports in import_graph.values())

    print(f"Total de nodos (módulos Atlas): {total_nodes}")
    print(f"Total de aristas (imports): {total_edges}")

    fan_in_counts = fan_in(import_graph)
    sorted_fan_in = sorted(fan_in_counts.items(), key=lambda item: item[1], reverse=True)
    print("\nTop 10 módulos por Fan-in:")
    for module, count in sorted_fan_in[:10]:
        print(f"- {module}: {count}")

    fan_out_counts = {node: len(imports) for node, imports in import_graph.items()}
    sorted_fan_out = sorted(fan_out_counts.items(), key=lambda item: item[1], reverse=True)
    print("\nTop 10 módulos por Fan-out:")
    for module, count in sorted_fan_out[:10]:
        print(f"- {module}: {count}")

    cycles = find_cycles(import_graph)
    if cycles:
        print("\nCiclos de importación encontrados:")
        for cycle in cycles:
            print(f"- {' -> '.join(cycle)}")
    else:
        print("\nNo se encontraron ciclos de importación.")

if __name__ == '__main__':
    main()
