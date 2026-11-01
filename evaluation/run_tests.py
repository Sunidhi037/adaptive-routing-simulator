import json
import time
import csv
import os

class MockGraph:
    def __init__(self, nodes, edges):
        self.nodes = nodes
        self.adj = {node: {} for node in nodes}
        for edge in edges:
            self.adj[edge['u']][edge['v']] = edge['weight']
            # Assuming undirected for standard routing test cases
            self.adj[edge['v']][edge['u']] = edge['weight']

def run_dijkstra(graph, source):
    import heapq
    start_time = time.perf_counter()
    distances = {node: float('inf') for node in graph.nodes}
    predecessors = {node: None for node in graph.nodes}
    distances[source] = 0
    pq = [(0, source)]
    
    while pq:
        current_dist, current_node = heapq.heappop(pq)
        if current_dist > distances[current_node]:
            continue
        for neighbor, weight in graph.adj[current_node].items():
            distance = current_dist + weight
            if distance < distances[neighbor]:
                distances[neighbor] = distance
                predecessors[neighbor] = current_node
                heapq.heappush(pq, (distance, neighbor))
                
    end_time = time.perf_counter()
    return distances, (end_time - start_time) * 1000

def run_bellman_ford(graph, source):
    start_time = time.perf_counter()
    distances = {node: float('inf') for node in graph.nodes}
    distances[source] = 0
    
    edges_list = []
    for u in graph.adj:
        for v, w in graph.adj[u].items():
            edges_list.append((u, v, w))
            
    for _ in range(len(graph.nodes) - 1):
        updated = False
        for u, v, w in edges_list:
            if distances[u] != float('inf') and distances[u] + w < distances[v]:
                distances[v] = distances[u] + w
                updated = True
        if not updated:
            break
            
    end_time = time.perf_counter()
    return distances, (end_time - start_time) * 1000

def execute_test_suite():
    with open('evaluation/test_cases.json', 'r') as f:
        data = json.load(f)
        
    results = []
    os.makedirs('.', exist_ok=True)
    
    for tc in data['test_cases']:
        g = MockGraph(tc['nodes'], tc['edges'])
        
        # Run Dijkstra
        d_costs, d_time = run_dijkstra(g, tc['source'])
        # Run Bellman-Ford
        bf_costs, bf_time = run_bellman_ford(g, tc['source'])
        
        for node in tc['nodes']:
            exp = tc['expected_costs'].get(node)
            d_val = d_costs.get(node)
            bf_val = bf_costs.get(node)
            
            # Normalize infinity representation for CSV
            d_out = d_val if d_val != float('inf') else "inf"
            bf_out = bf_val if bf_val != float('inf') else "inf"
            
            results.append({
                "test_id": tc['id'],
                "test_name": tc['name'],
                "node": node,
                "expected_cost": exp if exp is not None else "inf",
                "dijkstra_cost": d_out,
                "bellman_ford_cost": bf_out,
                "dijkstra_time_ms": round(d_time, 4),
                "bellman_ford_time_ms": round(bf_time, 4),
                "match": (d_val == bf_val) and (d_val == (exp if exp is not None else float('inf')))
            })
            
    with open('evaluation/results.csv', 'w', newline='') as csvfile:
        fieldnames = ["test_id", "test_name", "node", "expected_cost", "dijkstra_cost", "bellman_ford_cost", "dijkstra_time_ms", "bellman_ford_time_ms", "match"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r)
            
    print("Test execution complete. Results written to results.csv")

if __name__ == "__main__":
    execute_test_suite()